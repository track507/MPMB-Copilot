"""MPMB source code chunking for RAG indexing.

Consumes the AST analyzer report (scripts/analyze/reports/mpmb-analysis.json) for
authoritative object/function/add-call spans, scoped to discovered content registries,
and slices chunks at those boundaries. The unparseable `additional content syntax/`
templates are handled by a regex branch (they cannot be AST-parsed).

Every chunk gets three classification fields that drive retrieval:
        - edition:      "2014" | "2024" | "unknown"
        - source_tier:  "authoritative" | "official_example" | "community_example"
        - chunk_type:   "object_literal" | "function_call" | "function_definition" | "template_attribute"

Pipeline order: analyze -> chunk -> index (the chunker reads a fresh analyzer report).

Usage from app code:
    from app.core.chunker import mpmb_chunker
    result = mpmb_chunker.run_all()
"""

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import config
from app.logger import get_logger

logger = get_logger(__name__)


# * Bump when chunk boundaries/logic change; stamped onto the index for soft staleness
CHUNKER_VERSION = "2"


# Constants - lookup tables, not config

SKIP_PATTERNS = [
    "all_WotC_*.js",
    "*.min.js",
    "gulpfile.js",
    "package.json",
    "package-lock.json",
    "node_modules/**",
]

# ? object_type -> category for enrichment dispatch (no longer a filter)
OBJECT_TYPE_MAP = {
    "SpellsList": "spell",
    "ClassList": "class",
    "ClassSubList": "subclass",
    "RaceList": "race",
    "RaceSubList": "racial_variant",
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
    "PsionicsList": "psionic",
    "WeaponMasteriesList": "weapon_mastery",
    "DefaultEvalsList": "default_eval",
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


# Utilities


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

    if "additional content syntax" in path_str:
        return "authoritative"
    if "_functions" in path_str:
        return "authoritative"

    if "_variables" in path_str:
        return "official_example"

    if repo == "imports":
        if "WotC material" in path_str or "WotC 2024" in path_str:
            return "official_example"
        return "community_example"

    if "additional content" in path_str:
        return "community_example"

    if repo == "user":
        return "community_example"

    return "community_example"


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


# Analyzer-driven chunking (consumer pipeline)


ANALYSIS_REPORT_DEFAULT = Path("scripts/analyze/reports/mpmb-analysis.json")


def analyzer_repo_dirs() -> Dict[str, Path]:
    # ? analyzer repo keys map to the same data dirs config exposes
    return {
        "mpmb_source": Path(config.mpmb_source_dir),
        "mpmb_source_2024": Path(config.mpmb_source_2024_dir),
        "imports_source": Path(config.imports_source_dir),
    }


def load_analysis(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def tier_for_record(rec: Dict[str, Any], repo_dirs: Dict[str, Path]) -> str:
    repo_dir = repo_dirs[rec["repo"]]
    abs_path = repo_dir / rec["file"]
    repo_kind = "imports" if rec["repo"] == "imports_source" else "mpmb"
    return determine_source_tier(abs_path, {"repo": repo_kind})


def content_registry_types(objects: List[Dict[str, Any]], repo_dirs: Dict[str, Path]) -> set[str]:
    # ! an object_type is content if it gets a write in any example-tier file
    return {
        o["object_type"] for o in objects if tier_for_record(o, repo_dirs) in ("official_example", "community_example")
    }


def enrich_object(object_type: str, content: str, object_key: str) -> Dict[str, Any]:
    """Per-type metadata, lifted from the old ObjectAssignmentExtractor._extract_metadata."""
    meta: Dict[str, Any] = {
        "object_type": object_type,
        "object_key": object_key,
        "category": OBJECT_TYPE_MAP.get(object_type, "unknown"),
    }
    if m := re.search(r'\bname\s*:\s*["\']([^"\']+)["\']', content):
        meta["display_name"] = m.group(1)
    if m := re.search(r'\bsource\s*:\s*\[\s*\[\s*["\'](\w+)["\']\s*,\s*(\d+)', content):
        meta["source_book"] = m.group(1)
        meta["source_page"] = int(m.group(2))
    if object_type == "SpellsList":
        if m := re.search(r"\blevel\s*:\s*(\d+)", content):
            meta["spell_level"] = int(m.group(1))
        if m := re.search(r'\bschool\s*:\s*["\'](\w+)["\']', content):
            meta["spell_school"] = m.group(1)
        if m := re.search(r"\bclasses\s*:\s*\[([^\]]+)\]", content):
            meta["classes"] = re.findall(r'["\'](\w+)["\']', m.group(1))
    elif object_type == "FeatsList":
        if m := re.search(r'\btype\s*:\s*["\'](\w+)["\']', content):
            meta["feat_type"] = m.group(1)
    elif object_type == "MagicItemsList":
        if m := re.search(r'\brarity\s*:\s*["\']([^"\']+)["\']', content):
            meta["rarity"] = m.group(1)
        if m := re.search(r'\btype\s*:\s*["\']([^"\']+)["\']', content):
            meta["item_type"] = m.group(1)
    elif object_type == "RaceList":
        if m := re.search(r"\bsize\s*:\s*(\d+)", content):
            meta["size"] = int(m.group(1))
    return meta


def enrich_add(function_name: str, content: str) -> Dict[str, Any]:
    """Add* call metadata, lifted from the old FunctionCallExtractor._extract_metadata."""
    meta: Dict[str, Any] = {
        "function_name": function_name,
        "category": ADD_FUNCTION_MAP.get(function_name, "unknown"),
    }
    if function_name == "AddSubClass":
        if m := re.search(r'AddSubClass\s*\(\s*["\'](\w+)["\']\s*,\s*["\']([^"\']+)["\']', content):
            meta["parent_class"] = m.group(1)
            meta["object_key"] = m.group(2)
        if m := re.search(r'\bsubname\s*:\s*["\']([^"\']+)["\']', content):
            meta["display_name"] = m.group(1)
    elif function_name in ("AddRacialVariant", "AddBackgroundVariant"):
        if m := re.search(r'%s\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']' % function_name, content):
            meta["parent_key"] = m.group(1)
            meta["variant_key"] = m.group(2)
    elif function_name == "AddFeatureChoice":
        if m := re.search(r'AddFeatureChoice\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']', content):
            meta["parent_key"] = m.group(1)
            meta["feature_key"] = m.group(2)
    if m := re.search(r'\bsource\s*:\s*\[\s*\[\s*["\'](\w+)["\']\s*,\s*(\d+)', content):
        meta["source_book"] = m.group(1)
        meta["source_page"] = int(m.group(2))
    return meta


def _group_by_file(records: List[Dict[str, Any]]) -> Dict[tuple[str, str], List[Dict[str, Any]]]:
    grouped: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
    for r in records:
        grouped.setdefault((r["repo"], r["file"]), []).append(r)
    return grouped


def _read_normalized(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n").replace("\r", "\n")
    except OSError:
        return None


def _slice_lines(lines: List[str], start_line: int, end_line: int) -> str:
    return "\n".join(lines[start_line - 1 : end_line])


def chunk_objects(
    objects: List[Dict[str, Any]], content_types: set[str], repo_dirs: Dict[str, Path]
) -> List[CodeChunk]:
    chunks: List[CodeChunk] = []
    for (repo, file), recs in _group_by_file(objects).items():
        if should_skip(Path(file)):
            continue
        path = repo_dirs[repo] / file
        content = _read_normalized(path)
        if content is None:
            continue
        lines = content.split("\n")
        repo_kind = "imports" if repo == "imports_source" else "mpmb"
        edition = detect_edition(content, path, {"repo": repo_kind, "edition": "auto"})
        tier = determine_source_tier(path, {"repo": repo_kind})
        for o in recs:
            if o["object_type"] not in content_types:
                continue
            if o["end_line"] < o["line"] or o["end_line"] > len(lines):
                logger.warning(f"span out of range in {file}: {o['line']}-{o['end_line']}")
                continue
            text = _slice_lines(lines, o["line"], o["end_line"])
            chunks.append(
                CodeChunk(
                    content=text,
                    source_file=file,
                    source_repo=repo,
                    chunk_index=len(chunks),
                    start_line=o["line"],
                    end_line=o["end_line"],
                    chunk_type="object_literal",
                    edition=edition,
                    source_tier=tier,
                    metadata=enrich_object(o["object_type"], text, o["object_key"]),
                )
            )
    return chunks


def chunk_add_calls(add_calls: List[Dict[str, Any]], repo_dirs: Dict[str, Path]) -> List[CodeChunk]:
    chunks: List[CodeChunk] = []
    for (repo, file), recs in _group_by_file(add_calls).items():
        if should_skip(Path(file)):
            continue
        path = repo_dirs[repo] / file
        content = _read_normalized(path)
        if content is None:
            continue
        lines = content.split("\n")
        repo_kind = "imports" if repo == "imports_source" else "mpmb"
        edition = detect_edition(content, path, {"repo": repo_kind, "edition": "auto"})
        tier = determine_source_tier(path, {"repo": repo_kind})
        for c in recs:
            if c["end_line"] < c["line"] or c["end_line"] > len(lines):
                continue
            text = _slice_lines(lines, c["line"], c["end_line"])
            chunks.append(
                CodeChunk(
                    content=text,
                    source_file=file,
                    source_repo=repo,
                    chunk_index=len(chunks),
                    start_line=c["line"],
                    end_line=c["end_line"],
                    chunk_type="function_call",
                    edition=edition,
                    source_tier=tier,
                    metadata=enrich_add(c["function_name"], text),
                )
            )
    return chunks


# * Windowing for large engine functions (lifted thresholds)
WINDOW_THRESHOLD = 1500
WINDOW_SIZE = 800
WINDOW_OVERLAP = 150


def window_function(full_content: str) -> List[Dict[str, Any]]:
    """Split a large function into overlapping windows; lifted from _split_into_windows."""
    lines = full_content.split("\n")
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

    raw_windows: List[tuple[int, int]] = []
    start = 0
    while start < len(body_lines):
        total_chars = 0
        end = start
        while end < len(body_lines) and total_chars < WINDOW_SIZE:
            total_chars += len(body_lines[end]) + 1
            end += 1
        raw_windows.append((start, end))
        if end >= len(body_lines):
            break
        overlap_chars = 0
        next_start = end
        while next_start > start + 1 and overlap_chars < WINDOW_OVERLAP:
            next_start -= 1
            overlap_chars += len(body_lines[next_start]) + 1
        start = next_start

    total_windows = len(raw_windows)
    windows: List[Dict[str, Any]] = []
    for idx, (w_start, w_end) in enumerate(raw_windows):
        body_text = "\n".join(body_lines[w_start:w_end])
        window_content = (
            signature + "\n" + body_text if idx == 0 else signature + "\n\t// ... (continued)\n" + body_text
        )
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


def _jsdoc_start(lines: List[str], start_line: int) -> tuple[int, bool]:
    """If a /** */ block immediately precedes the function, extend the start back to it (1-based)."""
    i = start_line - 2  # ? 0-based index of the line just above the function keyword
    while i >= 0 and lines[i].strip() == "":
        i -= 1
    if i < 0 or not lines[i].strip().endswith("*/"):
        return start_line, False
    j = i
    while j >= 0 and "/**" not in lines[j]:
        j -= 1
    if j < 0:
        return start_line, False
    return j + 1, True


def chunk_functions(functions: List[Dict[str, Any]], repo_dirs: Dict[str, Path]) -> List[CodeChunk]:
    chunks: List[CodeChunk] = []
    for (repo, file), recs in _group_by_file(functions).items():
        if "_functions" not in file or should_skip(Path(file)):
            continue
        path = repo_dirs[repo] / file
        content = _read_normalized(path)
        if content is None:
            continue
        lines = content.split("\n")
        repo_kind = "imports" if repo == "imports_source" else "mpmb"
        edition = detect_edition(content, path, {"repo": repo_kind, "edition": "auto"})
        tier = determine_source_tier(path, {"repo": repo_kind})
        for fn in recs:
            if fn["end_line"] < fn["line"] or fn["end_line"] > len(lines):
                continue
            # ! top-level engine functions only (matches the old ^function); nesting depth is a deferred refinement
            if not lines[fn["line"] - 1].startswith("function"):
                continue
            start_line, has_jsdoc = _jsdoc_start(lines, fn["line"])
            full_content = _slice_lines(lines, start_line, fn["end_line"])
            base_meta: Dict[str, Any] = {
                "function_name": fn["name"],
                "category": "engine_function",
                "has_jsdoc": has_jsdoc,
                "size_chars": len(full_content),
                "size_lines": fn["end_line"] - start_line + 1,
                "file_context": file,
            }
            if len(full_content) <= WINDOW_THRESHOLD:
                chunks.append(
                    CodeChunk(
                        content=full_content,
                        source_file=file,
                        source_repo=repo,
                        chunk_index=len(chunks),
                        start_line=start_line,
                        end_line=fn["end_line"],
                        chunk_type="function_definition",
                        edition=edition,
                        source_tier=tier,
                        metadata={**base_meta, "window_index": 0, "total_windows": 1},
                    )
                )
            else:
                for win in window_function(full_content):
                    chunks.append(
                        CodeChunk(
                            content=win["content"],
                            source_file=file,
                            source_repo=repo,
                            chunk_index=len(chunks),
                            start_line=start_line + win["body_start_line"],
                            end_line=start_line + win["body_end_line"],
                            chunk_type="function_definition",
                            edition=edition,
                            source_tier=tier,
                            metadata={**base_meta, "window_index": win["index"], "total_windows": win["total"]},
                        )
                    )
    return chunks


# Syntax-template regex branch (the additional content syntax/ files do not AST-parse)


_TEMPLATE_ATTRIBUTE = re.compile(r"^\t*(\w+)\s*:\s*(.+?)(?:,\s*)?$\s*(/\*[\s\S]*?\*/)", re.MULTILINE)
_TEMPLATE_CATEGORY = re.compile(r"//\s*>{3,}(.+?)>{3,}\s*//")


def _detect_template_object_type(file_path: str) -> str:
    name = Path(file_path).stem.lower()
    for obj_type, category in OBJECT_TYPE_MAP.items():
        if obj_type.lower() in name or category in name:
            return obj_type
    if "common attributes" in name:
        return "_common_attributes"
    if "common spell" in name:
        return "_common_spell_list"
    return "unknown"


def extract_syntax_templates(
    content: str, file_path: str, edition: str, source_tier: str, source_repo: str
) -> List[CodeChunk]:
    """Documented attribute blocks from syntax templates; lifted from the old SyntaxTemplateExtractor."""
    chunks: List[CodeChunk] = []
    object_type = _detect_template_object_type(file_path)

    categories: Dict[int, str] = {}
    for match in _TEMPLATE_CATEGORY.finditer(content):
        line_num = content[: match.start()].count("\n") + 1
        categories[line_num] = match.group(1).strip()

    for match in _TEMPLATE_ATTRIBUTE.finditer(content):
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


# Main Chunker


class MPMBChunker:
    """Builds chunks by consuming the analyzer report (object/add/function spans) plus the regex template branch."""

    def __init__(self):
        self.stats: Dict[str, Any] = {
            "chunks_created": 0,
            "by_type": {},
            "by_edition": {},
            "by_tier": {},
            "by_category": {},
        }

    def run_all(self, report_path: Optional[Path] = None, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Build chunks from the analyzer report + the syntax-template branch, then write chunked_output."""
        report_path = report_path or ANALYSIS_REPORT_DEFAULT
        output_dir = output_dir or config.chunked_output_path
        repo_dirs = analyzer_repo_dirs()

        if not report_path.exists():
            raise FileNotFoundError(
                f"Analyzer report not found: {report_path}. Run the analyzer first: pnpm run analyze"
            )

        report = load_analysis(report_path)
        content_types = content_registry_types(report.get("objects", []), repo_dirs)

        chunks: List[CodeChunk] = []
        chunks += chunk_objects(report.get("objects", []), content_types, repo_dirs)
        chunks += chunk_add_calls(report.get("add_calls", []), repo_dirs)
        chunks += chunk_functions(report.get("functions", []), repo_dirs)
        chunks += self._chunk_syntax_templates()

        for i, c in enumerate(chunks):
            c.chunk_index = i

        self._tally(chunks)
        output_files = self._write_outputs(chunks, output_dir)
        return {
            "stats": self.stats,
            "chunker_version": CHUNKER_VERSION,
            "output_dir": str(output_dir),
            "output_files": output_files,
        }

    def _chunk_syntax_templates(self) -> List[CodeChunk]:
        chunks: List[CodeChunk] = []
        for cfg in config.source_configs:
            if cfg["repo"] != "mpmb":
                continue
            syntax_dir = cfg["path"] / "additional content syntax"
            if not syntax_dir.exists():
                continue
            for fp in sorted(syntax_dir.glob("*.js")):
                if should_skip(fp):
                    continue
                content = _read_normalized(fp)
                if content is None:
                    continue
                rel = str(fp.relative_to(cfg["path"]))
                edition = detect_edition(content, fp, cfg)
                tier = determine_source_tier(fp, cfg)
                chunks += extract_syntax_templates(content, rel, edition, tier, cfg["repo"])
        return chunks

    def _write_outputs(self, chunks: List[CodeChunk], output_dir: Path) -> List[str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        # ! clear stale chunk files so the indexer (globs *.json) does not read old + new
        for old in output_dir.glob("*.json"):
            old.unlink()
        by_type: Dict[str, List[CodeChunk]] = {}
        for c in chunks:
            by_type.setdefault(c.chunk_type, []).append(c)
        written: List[str] = []
        for ctype, group in sorted(by_type.items()):
            fname = f"{ctype}.json"
            # ! stream to the file instead of building one giant json string (avoids OOM on big groups)
            with (output_dir / fname).open("w", encoding="utf-8") as f:
                json.dump([c.to_dict() for c in group], f, indent=2, ensure_ascii=False)
                f.write("\n")
            written.append(fname)
        logger.info(f"Wrote {len(chunks)} chunks to {output_dir} ({len(written)} files)")
        return written

    def _tally(self, chunks: List[CodeChunk]) -> None:
        self.stats["chunks_created"] = len(chunks)
        for c in chunks:
            self.stats["by_type"][c.chunk_type] = self.stats["by_type"].get(c.chunk_type, 0) + 1
            self.stats["by_edition"][c.edition] = self.stats["by_edition"].get(c.edition, 0) + 1
            self.stats["by_tier"][c.source_tier] = self.stats["by_tier"].get(c.source_tier, 0) + 1
            cat = c.metadata.get("category", "unknown")
            self.stats["by_category"][cat] = self.stats["by_category"].get(cat, 0) + 1

    def get_stats_summary(self) -> str:
        """Formatted stats string."""
        lines = [f"Total chunks: {self.stats['chunks_created']}"]
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
