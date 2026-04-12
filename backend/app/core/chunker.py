"""MPMB source code chunking for RAG indexing.

Extracts semantic chunks from MPMB JavaScript files across multiple
repositories and editions. All file paths come from app.config.config.

Every chunk gets three classification fields that drive retrieval:
        - edition:      "2014" | "2024" | "unknown"
        - source_tier:  "authoritative" | "official_example" | "community_example"
        - chunk_type:   "object_literal" | "function_call" | "function_definition" | "template_attribute"

Source tier rules:
        authoritative       - syntax templates, engine functions, Adobe docs
                        These define what is VALID.
        official_example    - safety-orange Imports (WotC material), built-in variables
                        These show how the AUTHORS do it.
        community_example   - MPMB additional content, Homebrew, user scripts
                        These show how EVERYONE ELSE does it.

Usage from app code:
    from app.core.chunker import mpmb_chunker
    result = mpmb_chunker.run_all()

Usage with overrides (CLI or testing):
    chunker = MPMBChunker()
    result = chunker.run_all(
        source_configs=custom_configs,
        output_dir=Path("./custom/output"),
    )
"""

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import config
from app.logger import get_logger

logger = get_logger(__name__)


# Constants - lookup tables, not config

SKIP_PATTERNS = [
    "all_WotC_*.js",
    "*.min.js",
    "gulpfile.js",
    "package.json",
    "package-lock.json",
    "node_modules/**",
]

OBJECT_TYPE_MAP = {
    "SpellsList": "spell",
    "ClassList": "class",
    "ClassSubList": "subclass",
    "RaceList": "race",
    "FeatsList": "feat",
    "MagicItemsList": "magic_item",
    "CreatureList": "creature",
    "BackgroundList": "background",
    "BackgroundFeatureList": "background_feature",
    "CompanionList": "companion",
    "WeaponsList": "weapon",
    "ArmourList": "armor",
    "AmmoList": "ammunition",
    "GearList": "gear",
    "ToolsList": "tool",
    "PacksList": "pack",
    "SourceList": "source",
}

ADD_FUNCTION_MAP = {
    "AddSubClass": "subclass",
    "AddFeatureChoice": "feature_choice",
    "AddBackgroundVariant": "background_variant",
    "AddRacialVariant": "racial_variant",
    "AddWarlockInvocation": "warlock_invocation",
    "AddFightingStyle": "fighting_style",
    "AddWarlockPactBoon": "warlock_pact_boon",
}


# Data Classes


@dataclass
class CodeChunk:
    """A single chunk of code for RAG indexing."""

    content: str
    source_file: str
    source_repo: str
    chunk_index: int
    start_line: int
    end_line: int
    chunk_type: str
    edition: str
    source_tier: str  # "authoritative" | "official_example" | "community_example"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FileContext:
    """Metadata extracted from a file's header."""

    filename: str = ""
    required_version: Optional[str] = None
    description: Optional[str] = None


# Utilities


def find_matching_brace(content: str, start_pos: int) -> int:
    """Find the position after the matching closing brace/paren.

    Handles nesting, skips strings, regexes, and comments.
    Returns -1 if no match found.
    """
    open_char = content[start_pos]
    close_char = "}" if open_char == "{" else ")"
    depth = 0
    i = start_pos
    length = len(content)

    while i < length:
        c = content[i]

        # Skip single-line comments
        if c == "/" and i + 1 < length and content[i + 1] == "/":
            while i < length and content[i] != "\n":
                i += 1
            continue

        # Skip multi-line comments
        if c == "/" and i + 1 < length and content[i + 1] == "*":
            i += 2
            while i + 1 < length and not (content[i] == "*" and content[i + 1] == "/"):
                i += 1
            i += 2
            continue

        # Skip strings
        if c in ("'", '"'):
            quote = c
            i += 1
            while i < length and content[i] != quote:
                if content[i] == "\\":
                    i += 1
                i += 1
            i += 1
            continue

        # Skip regex literals
        if c == "/" and i > 0:
            lookback = content[max(0, i - 5) : i].rstrip()
            if lookback and lookback[-1] in "=([!&|;{},:\n":
                i += 1
                while i < length and content[i] != "/":
                    if content[i] == "\\":
                        i += 1
                    i += 1
                i += 1
                while i < length and content[i] in "gimsuvy":
                    i += 1
                continue

        if c == open_char:
            depth += 1
        elif c == close_char:
            depth -= 1
            if depth == 0:
                end = i + 1
                remaining = content[end : end + 5].lstrip()
                if remaining.startswith(";"):
                    end = content.index(";", end) + 1
                return end

        i += 1

    return -1


def detect_edition(content: str, file_path: Path, source_config: dict) -> str:
    """Detect edition from file content and path context."""
    if source_config.get("edition") not in ("auto", None):
        return source_config["edition"]

    path_str = str(file_path)
    if "WotC 2024" in path_str:
        return "2024"
    if "WotC material" in path_str:
        return "2014"
    if "Homebrew" in path_str:
        return "unknown"

    version_match = re.search(r'RequiredSheetVersion\(["\'](\d+)', content)
    if version_match:
        major = int(version_match.group(1))
        return "2024" if major >= 24 else "2014"

    return "unknown"


def determine_source_tier(file_path: Path, source_config: dict) -> str:
    """Determine the source tier for a file based on its location.

    Returns:
            "authoritative"      - syntax templates, engine functions
            "official_example"   - safety-orange Imports (WotC), built-in variables
            "community_example"  - additional content, homebrew, user scripts
    """
    path_str = str(file_path)
    repo = source_config.get("repo", "")

    # Syntax templates and engine functions are always authoritative
    if "additional content syntax" in path_str:
        return "authoritative"
    if "_functions" in path_str:
        return "authoritative"

    # Built-in variables (SRD content) are official examples
    if "_variables" in path_str:
        return "official_example"

    # safety-orange Imports - WotC content is official, Homebrew is community
    if repo == "imports":
        if "WotC material" in path_str or "WotC 2024" in path_str:
            return "official_example"
        return "community_example"

    # MPMB additional content examples - these are 3rd-party transcriptions
    if "additional content" in path_str:
        return "community_example"

    # User-provided content
    if repo == "user":
        return "community_example"

    # Default fallback
    return "community_example"


def extract_file_context(content: str) -> FileContext:
    """Extract header metadata from a file."""
    ctx = FileContext()

    match = re.search(r'var\s+iFileName\s*=\s*["\']([^"\']+)["\']', content)
    if match:
        ctx.filename = match.group(1)

    match = re.search(r'RequiredSheetVersion\(["\']?([^"\')\s]+)', content)
    if match:
        ctx.required_version = match.group(1)

    match = re.search(r"//\s*(This file .+?)[\r\n]", content[:2000])
    if match:
        ctx.description = match.group(1).strip()

    return ctx


def should_skip(filepath: Path) -> bool:
    """Check if a file should be skipped."""
    name = filepath.name
    for pattern in SKIP_PATTERNS:
        if "*" in pattern:
            prefix = pattern.split("*")[0]
            suffix = pattern.split("*")[-1]
            if name.startswith(prefix) and name.endswith(suffix):
                return True
        elif name == pattern:
            return True
    return False


# Extractors


class ObjectAssignmentExtractor:
    """Extracts ObjectType["key"] = { ... }; patterns."""

    BRACKET_PATTERN = re.compile(r'^(\w+)\s*\[\s*["\']([^"\']+)["\']\s*\]\s*=\s*\{', re.MULTILINE)
    DOT_PATTERN = re.compile(r"^(\w+)\.(\w+)\s*=\s*\{", re.MULTILINE)

    def extract(
        self, content: str, file_path: str, edition: str, source_tier: str, source_repo: str, file_context: FileContext
    ) -> List[CodeChunk]:
        chunks = []

        for pattern in [self.BRACKET_PATTERN, self.DOT_PATTERN]:
            for match in pattern.finditer(content):
                obj_type = match.group(1)
                obj_key = match.group(2)

                if obj_type not in OBJECT_TYPE_MAP:
                    continue

                brace_pos = content.index("{", match.start())
                end_pos = find_matching_brace(content, brace_pos)
                if end_pos == -1:
                    continue

                chunk_content = content[match.start() : end_pos]
                start_line = content[: match.start()].count("\n") + 1
                end_line = content[:end_pos].count("\n") + 1

                metadata = self._extract_metadata(chunk_content, obj_type, obj_key)
                metadata["file_context"] = file_context.filename or file_path
                if file_context.description:
                    metadata["file_description"] = file_context.description

                chunks.append(
                    CodeChunk(
                        content=chunk_content,
                        source_file=file_path,
                        source_repo=source_repo,
                        chunk_index=len(chunks),
                        start_line=start_line,
                        end_line=end_line,
                        chunk_type="object_literal",
                        edition=edition,
                        source_tier=source_tier,
                        metadata=metadata,
                    )
                )

        return chunks

    def _extract_metadata(self, content: str, obj_type: str, obj_key: str) -> Dict[str, Any]:
        meta: Dict[str, Any] = {
            "object_type": obj_type,
            "object_key": obj_key,
            "category": OBJECT_TYPE_MAP.get(obj_type, "unknown"),
        }

        m = re.search(r'\bname\s*:\s*["\']([^"\']+)["\']', content)
        if m:
            meta["display_name"] = m.group(1)

        m = re.search(r'\bsource\s*:\s*\[\s*\[\s*["\'](\w+)["\']\s*,\s*(\d+)', content)
        if m:
            meta["source_book"] = m.group(1)
            meta["source_page"] = int(m.group(2))

        if obj_type == "SpellsList":
            m = re.search(r"\blevel\s*:\s*(\d+)", content)
            if m:
                meta["spell_level"] = int(m.group(1))
            m = re.search(r'\bschool\s*:\s*["\'](\w+)["\']', content)
            if m:
                meta["spell_school"] = m.group(1)
            m = re.search(r"\bclasses\s*:\s*\[([^\]]+)\]", content)
            if m:
                meta["classes"] = re.findall(r'["\'](\w+)["\']', m.group(1))
        elif obj_type == "FeatsList":
            m = re.search(r'\btype\s*:\s*["\'](\w+)["\']', content)
            if m:
                meta["feat_type"] = m.group(1)
        elif obj_type == "MagicItemsList":
            m = re.search(r'\brarity\s*:\s*["\']([^"\']+)["\']', content)
            if m:
                meta["rarity"] = m.group(1)
            m = re.search(r'\btype\s*:\s*["\']([^"\']+)["\']', content)
            if m:
                meta["item_type"] = m.group(1)
        elif obj_type == "RaceList":
            m = re.search(r"\bsize\s*:\s*(\d+)", content)
            if m:
                meta["size"] = int(m.group(1))

        return meta


class FunctionCallExtractor:
    """Extracts AddSubClass(...), AddFeatureChoice(...), etc."""

    PATTERN = re.compile(r"^(Add\w+)\s*\(", re.MULTILINE)

    def extract(
        self, content: str, file_path: str, edition: str, source_tier: str, source_repo: str, file_context: FileContext
    ) -> List[CodeChunk]:
        chunks = []

        for match in self.PATTERN.finditer(content):
            func_name = match.group(1)
            if func_name not in ADD_FUNCTION_MAP:
                continue

            paren_pos = content.index("(", match.start())
            end_pos = find_matching_brace(content, paren_pos)
            if end_pos == -1:
                continue

            chunk_content = content[match.start() : end_pos]
            start_line = content[: match.start()].count("\n") + 1
            end_line = content[:end_pos].count("\n") + 1

            metadata = self._extract_metadata(chunk_content, func_name)
            metadata["file_context"] = file_context.filename or file_path
            if file_context.description:
                metadata["file_description"] = file_context.description

            chunks.append(
                CodeChunk(
                    content=chunk_content,
                    source_file=file_path,
                    source_repo=source_repo,
                    chunk_index=len(chunks),
                    start_line=start_line,
                    end_line=end_line,
                    chunk_type="function_call",
                    edition=edition,
                    source_tier=source_tier,
                    metadata=metadata,
                )
            )

        return chunks

    def _extract_metadata(self, content: str, func_name: str) -> Dict[str, Any]:
        meta: Dict[str, Any] = {
            "function_name": func_name,
            "category": ADD_FUNCTION_MAP.get(func_name, "unknown"),
        }

        if func_name == "AddSubClass":
            m = re.search(r'AddSubClass\s*\(\s*["\'](\w+)["\']\s*,\s*["\']([^"\']+)["\']', content)
            if m:
                meta["parent_class"] = m.group(1)
                meta["object_key"] = m.group(2)
            m = re.search(r'\bsubname\s*:\s*["\']([^"\']+)["\']', content)
            if m:
                meta["display_name"] = m.group(1)
        elif func_name in ("AddRacialVariant", "AddBackgroundVariant"):
            m = re.search(r'%s\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']' % func_name, content)
            if m:
                meta["parent_key"] = m.group(1)
                meta["variant_key"] = m.group(2)
        elif func_name == "AddFeatureChoice":
            m = re.search(r'AddFeatureChoice\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']', content)
            if m:
                meta["parent_key"] = m.group(1)
                meta["feature_key"] = m.group(2)

        m = re.search(r'\bsource\s*:\s*\[\s*\[\s*["\'](\w+)["\']\s*,\s*(\d+)', content)
        if m:
            meta["source_book"] = m.group(1)
            meta["source_page"] = int(m.group(2))

        return meta


class FunctionDefinitionExtractor:
    """Extracts standalone function definitions from engine files.

    Small functions (<= WINDOW_THRESHOLD chars) produce a single chunk.
    Larger functions are split into overlapping windows so each chunk
    is competitive in hybrid search against the smaller syntax-template
    chunks.  Every window carries the function signature as a header so
    it is independently grounded (function name, parameters, JSDoc).
    """

    PATTERN = re.compile(r"^function\s+(\w+)\s*\([^)]*\)\s*\{", re.MULTILINE)

    # Windowing parameters
    WINDOW_THRESHOLD = 1500  # Functions larger than this get windowed
    WINDOW_SIZE = 800  # Target body chars per window
    WINDOW_OVERLAP = 150  # Overlap chars between consecutive windows

    def extract(
        self,
        content: str,
        file_path: str,
        edition: str,
        source_tier: str,
        source_repo: str,
        file_context: FileContext,
    ) -> List[CodeChunk]:
        chunks = []

        for match in self.PATTERN.finditer(content):
            func_name = match.group(1)
            func_start = match.start()

            brace_pos = content.index("{", match.start())
            end_pos = find_matching_brace(content, brace_pos)
            if end_pos == -1:
                continue

            # Look for JSDoc before the function
            preceding = content[max(0, func_start - 1000) : func_start]
            jsdoc_match = re.search(r"(/\*\*[\s\S]*?\*/)\s*$", preceding)
            if jsdoc_match:
                func_start = func_start - len(preceding) + jsdoc_match.start()

            full_content = content[func_start:end_pos]
            full_start_line = content[:func_start].count("\n") + 1
            full_end_line = content[:end_pos].count("\n") + 1
            full_size = end_pos - func_start
            full_lines = full_end_line - full_start_line + 1

            base_metadata = {
                "function_name": func_name,
                "category": "engine_function",
                "has_jsdoc": bool(jsdoc_match),
                "size_chars": full_size,
                "size_lines": full_lines,
                "file_context": file_context.filename or file_path,
            }

            if len(full_content) <= self.WINDOW_THRESHOLD:
                # Small function - single chunk
                chunks.append(
                    CodeChunk(
                        content=full_content,
                        source_file=file_path,
                        source_repo=source_repo,
                        chunk_index=len(chunks),
                        start_line=full_start_line,
                        end_line=full_end_line,
                        chunk_type="function_definition",
                        edition=edition,
                        source_tier=source_tier,
                        metadata={**base_metadata, "window_index": 0, "total_windows": 1},
                    )
                )
            else:
                # Large function - split into overlapping windows
                windows = self._split_into_windows(full_content)
                for win in windows:
                    chunks.append(
                        CodeChunk(
                            content=win["content"],
                            source_file=file_path,
                            source_repo=source_repo,
                            chunk_index=len(chunks),
                            start_line=full_start_line + win["body_start_line"],
                            end_line=full_start_line + win["body_end_line"],
                            chunk_type="function_definition",
                            edition=edition,
                            source_tier=source_tier,
                            metadata={
                                **base_metadata,
                                "window_index": win["index"],
                                "total_windows": win["total"],
                            },
                        )
                    )

        return chunks

    def _split_into_windows(self, full_content: str) -> List[Dict[str, Any]]:
        """Split a function into overlapping windows by lines.

        Each window gets the function signature (including JSDoc)
        prepended so it is independently searchable and grounded.

        Returns a list of dicts with keys:
            content, index, total, body_start_line, body_end_line
        """
        lines = full_content.split("\n")

        # Extract signature: everything up to and including the opening brace
        sig_end = 0
        for i, line in enumerate(lines):
            if "{" in line:
                sig_end = i + 1
                break
        signature = "\n".join(lines[:sig_end])
        body_lines = lines[sig_end:]

        if not body_lines:
            return [
                {"content": full_content, "index": 0, "total": 1, "body_start_line": 0, "body_end_line": len(lines) - 1}
            ]

        # Build windows over body_lines
        raw_windows: List[tuple[int, int]] = []  # (start_idx, end_idx) into body_lines
        start = 0

        while start < len(body_lines):
            total_chars = 0
            end = start
            while end < len(body_lines) and total_chars < self.WINDOW_SIZE:
                total_chars += len(body_lines[end]) + 1
                end += 1

            raw_windows.append((start, end))

            if end >= len(body_lines):
                break

            # Step forward, leaving overlap
            overlap_chars = 0
            next_start = end
            while next_start > start + 1 and overlap_chars < self.WINDOW_OVERLAP:
                next_start -= 1
                overlap_chars += len(body_lines[next_start]) + 1

            start = next_start

        # Build final window contents
        total_windows = len(raw_windows)
        windows = []
        for idx, (w_start, w_end) in enumerate(raw_windows):
            body_text = "\n".join(body_lines[w_start:w_end])

            if idx == 0:
                window_content = signature + "\n" + body_text
            else:
                window_content = signature + "\n\t// ... (continued)\n" + body_text

            windows.append(
                {
                    "content": window_content,
                    "index": idx,
                    "total": total_windows,
                    "body_start_line": sig_end + w_start,
                    "body_end_line": sig_end + w_end - 1,
                }
            )

        return windows


class SyntaxTemplateExtractor:
    """Extracts documented attributes from syntax template files."""

    ATTRIBUTE_BLOCK = re.compile(r"^\t*(\w+)\s*:\s*(.+?)(?:,\s*)?$\s*(/\*[\s\S]*?\*/)", re.MULTILINE)
    CATEGORY = re.compile(r"//\s*>{3,}(.+?)>{3,}\s*//")

    def extract(
        self, content: str, file_path: str, edition: str, source_tier: str, source_repo: str, file_context: FileContext
    ) -> List[CodeChunk]:
        chunks = []
        object_type = self._detect_object_type(file_path)

        categories: Dict[int, str] = {}
        for match in self.CATEGORY.finditer(content):
            line_num = content[: match.start()].count("\n") + 1
            categories[line_num] = match.group(1).strip()

        for match in self.ATTRIBUTE_BLOCK.finditer(content):
            attr_name = match.group(1)
            attr_example = match.group(2).strip()
            attr_comment = match.group(3)

            if "// REQUIRED //" not in attr_comment and "// OPTIONAL //" not in attr_comment:
                continue

            start_line = content[: match.start()].count("\n") + 1
            end_line = content[: match.end()].count("\n") + 1

            category = "General"
            for cat_line, cat_name in sorted(categories.items(), reverse=True):
                if cat_line < start_line:
                    category = cat_name
                    break

            is_required = "// REQUIRED //" in attr_comment
            type_match = re.search(r"TYPE:\s*(.+?)(?:\n|\*/)", attr_comment)
            use_match = re.search(r"USE:\s*(.+?)(?:\n|\*/)", attr_comment)
            change_match = re.search(r"CHANGE:\s*(.+?)(?:\n|\*/)", attr_comment)

            chunks.append(
                CodeChunk(
                    content=match.group(0),
                    source_file=file_path,
                    source_repo=source_repo,
                    chunk_index=len(chunks),
                    start_line=start_line,
                    end_line=end_line,
                    chunk_type="template_attribute",
                    edition=edition,
                    source_tier=source_tier,
                    metadata={
                        "attribute_name": attr_name,
                        "object_type": object_type,
                        "category": category,
                        "is_required": is_required,
                        "attribute_type": type_match.group(1).strip() if type_match else None,
                        "usage": use_match.group(1).strip() if use_match else None,
                        "change_note": change_match.group(1).strip() if change_match else None,
                        "example_value": attr_example[:200],
                        "syntax_section": "template_documentation",
                    },
                )
            )

        return chunks

    def _detect_object_type(self, file_path: str) -> str:
        name = Path(file_path).stem.lower()
        for obj_type, category in OBJECT_TYPE_MAP.items():
            if obj_type.lower() in name or category in name:
                return obj_type
        if "common attributes" in name:
            return "_common_attributes"
        if "common spell" in name:
            return "_common_spell_list"
        return "unknown"


# Main Chunker


class MPMBChunker:
    """Orchestrates chunking across all source repositories."""

    def __init__(self):
        self.obj_extractor = ObjectAssignmentExtractor()
        self.func_call_extractor = FunctionCallExtractor()
        self.func_def_extractor = FunctionDefinitionExtractor()
        self.syntax_extractor = SyntaxTemplateExtractor()
        self.stats: Dict[str, Any] = {
            "files_processed": 0,
            "files_skipped": 0,
            "chunks_created": 0,
            "by_type": {},
            "by_edition": {},
            "by_tier": {},
            "by_category": {},
        }

    def chunk_file(
        self,
        filepath: Path,
        source_config: dict,
        relative_to: Optional[Path] = None,
    ) -> List[CodeChunk]:
        """Chunk a single file using the appropriate extractors."""
        if should_skip(filepath):
            self.stats["files_skipped"] += 1
            return []

        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.error(f"Error reading {filepath.name}: {e}")
            return []

        content = content.replace("\r\n", "\n").replace("\r", "\n")

        rel_path = str(filepath.relative_to(relative_to)) if relative_to else filepath.name
        file_context = extract_file_context(content)
        edition = detect_edition(content, filepath, source_config)
        source_tier = determine_source_tier(filepath, source_config)

        chunks: List[CodeChunk] = []
        path_str = str(filepath)

        # Common args for all extractors
        ext_args = (content, rel_path, edition, source_tier, source_config["repo"], file_context)

        if "additional content syntax" in path_str:
            chunks = self.syntax_extractor.extract(*ext_args)
        elif "_functions" in path_str:
            chunks = self.func_def_extractor.extract(*ext_args)
        else:
            obj_chunks = self.obj_extractor.extract(*ext_args)
            call_chunks = self.func_call_extractor.extract(*ext_args)
            for i, chunk in enumerate(call_chunks):
                chunk.chunk_index = len(obj_chunks) + i
            chunks = obj_chunks + call_chunks

        if chunks:
            self.stats["files_processed"] += 1
            self.stats["chunks_created"] += len(chunks)
            for chunk in chunks:
                self.stats["by_type"][chunk.chunk_type] = self.stats["by_type"].get(chunk.chunk_type, 0) + 1
                self.stats["by_edition"][chunk.edition] = self.stats["by_edition"].get(chunk.edition, 0) + 1
                self.stats["by_tier"][chunk.source_tier] = self.stats["by_tier"].get(chunk.source_tier, 0) + 1
                cat = chunk.metadata.get("category", "unknown")
                self.stats["by_category"][cat] = self.stats["by_category"].get(cat, 0) + 1

        return chunks

    def chunk_directory(
        self,
        directory: Path,
        source_config: dict,
        pattern: str = "**/*.js",
    ) -> List[CodeChunk]:
        """Chunk all JS files in a directory."""
        all_chunks: List[CodeChunk] = []
        js_files = sorted(directory.glob(pattern))
        logger.info(f"Scanning {directory.name}/ - {len(js_files)} .js files")

        for filepath in js_files:
            if should_skip(filepath):
                self.stats["files_skipped"] += 1
                continue
            chunks = self.chunk_file(filepath, source_config, relative_to=source_config["path"])
            if chunks:
                logger.debug(f"  {filepath.name}: {len(chunks)} chunks")
            all_chunks.extend(chunks)

        return all_chunks

    def save_chunks(self, chunks: List[CodeChunk], output_dir: Path, filename: str) -> Path:
        """Save chunks to JSON."""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([c.to_dict() for c in chunks], f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(chunks)} chunks -> {output_path}")
        return output_path

    def run_all(
        self,
        source_configs: Optional[List[dict]] = None,
        output_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Run the full chunking pipeline.

        Args:
                source_configs: Defaults to config.source_configs.
                output_dir: Defaults to config.chunked_output_path.

        Returns:
                Dict with stats and list of output filenames.
        """
        source_configs = source_configs or config.source_configs
        output_dir = output_dir or config.chunked_output_path
        output_files: List[str] = []

        if not source_configs:
            logger.warning("No source directories found.")
            return {"error": "no_sources", "stats": self.stats}

        # 1. Syntax Templates
        for source_config in source_configs:
            if source_config["repo"] != "mpmb":
                continue
            syntax_dir = source_config["path"] / "additional content syntax"
            if syntax_dir.exists():
                logger.info(f"Chunking syntax templates: {source_config['description']}")
                chunks = self.chunk_directory(syntax_dir, source_config, pattern="*.js")
                if chunks:
                    fname = f"syntax_templates_{source_config['edition']}.json"
                    self.save_chunks(chunks, output_dir, fname)
                    output_files.append(fname)

        # 2. Engine Functions
        for source_config in source_configs:
            if source_config["repo"] != "mpmb":
                continue
            func_dir = source_config["path"] / "_functions"
            if func_dir.exists():
                logger.info(f"Chunking engine functions: {source_config['description']}")
                chunks = self.chunk_directory(func_dir, source_config, pattern="*.js")
                if chunks:
                    fname = f"engine_functions_{source_config['edition']}.json"
                    self.save_chunks(chunks, output_dir, fname)
                    output_files.append(fname)

        # 3. Built-in Variables (master only)
        for source_config in source_configs:
            if source_config["key"] != "mpmb_master":
                continue
            vars_dir = source_config["path"] / "_variables"
            if vars_dir.exists():
                logger.info("Chunking built-in variables")
                chunks = self.chunk_directory(vars_dir, source_config, pattern="*.js")
                if chunks:
                    self.save_chunks(chunks, output_dir, "builtin_variables.json")
                    output_files.append("builtin_variables.json")

        # 4. Imports Content
        for source_config in source_configs:
            if source_config["repo"] != "imports":
                continue
            imports_path = source_config["path"]

            for subfolder, edition_tag, out_name in [
                ("WotC material", "2014", "imports_2014.json"),
                ("WotC 2024", "2024", "imports_2024.json"),
                ("Homebrew", "unknown", "imports_homebrew.json"),
            ]:
                sub = imports_path / subfolder
                if sub.exists():
                    logger.info(f"Chunking imports: {subfolder}")
                    chunks = self.chunk_directory(sub, {**source_config, "edition": edition_tag}, pattern="*.js")
                    if chunks:
                        self.save_chunks(chunks, output_dir, out_name)
                        output_files.append(out_name)

        # 5. Additional Content Examples (master)
        for source_config in source_configs:
            if source_config["key"] != "mpmb_master":
                continue
            content_dir = source_config["path"] / "additional content"
            if content_dir.exists():
                logger.info("Chunking additional content examples")
                all_content: List[CodeChunk] = []
                for subdir in sorted(content_dir.iterdir()):
                    if subdir.is_dir() and subdir.name != "syntax":
                        all_content.extend(self.chunk_directory(subdir, source_config, pattern="*.js"))
                if all_content:
                    self.save_chunks(all_content, output_dir, "additional_content_examples.json")
                    output_files.append("additional_content_examples.json")

        # 6. User-provided sources
        for source_config in source_configs:
            if source_config["repo"] != "user":
                continue
            logger.info(f"Chunking user source: {source_config['path']}")
            chunks = self.chunk_directory(source_config["path"], source_config, pattern="**/*.js")
            if chunks:
                fname = f"user_{source_config['key']}.json"
                self.save_chunks(chunks, output_dir, fname)
                output_files.append(fname)

        return {
            "stats": self.stats,
            "output_dir": str(output_dir),
            "output_files": output_files,
        }

    def get_stats_summary(self) -> str:
        """Formatted stats string."""
        lines = [
            f"Files processed: {self.stats['files_processed']}",
            f"Files skipped:   {self.stats['files_skipped']}",
            f"Total chunks:    {self.stats['chunks_created']}",
        ]
        for label, key in [
            ("By chunk type", "by_type"),
            ("By edition", "by_edition"),
            ("By source tier", "by_tier"),
            ("By category", "by_category"),
        ]:
            data = self.stats.get(key, {})
            if data:
                lines.append(f"\n{label}:")
                for k, v in sorted(data.items(), key=lambda x: -x[1]):
                    lines.append(f"  {k:30s} {v:5d}")
        return "\n".join(lines)


# Global instance
mpmb_chunker = MPMBChunker()
