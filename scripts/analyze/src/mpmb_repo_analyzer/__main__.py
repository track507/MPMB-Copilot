from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


OBJECT_TYPES = (
    "SpellsList",
    "ClassList",
    "ClassSubList",
    "RaceList",
    "RaceSubList",
    "FeatsList",
    "MagicItemsList",
    "CreatureList",
    "BackgroundList",
    "BackgroundFeatureList",
    "CompanionList",
    "WeaponsList",
    "ArmourList",
    "AmmoList",
    "GearList",
    "ToolsList",
    "PacksList",
    "SourceList",
    "PsionicsList",
    "WeaponMasteriesList",
    "DefaultEvalsList",
)

ADD_DECLARATIONS = (
    "AddSubClass",
    "AddFeatureChoice",
    "AddBackgroundVariant",
    "AddRacialVariant",
    "AddWarlockInvocation",
    "AddFightingStyle",
    "AddWarlockPactBoon",
)

SKIP_NAMES = {"gulpfile.js", "package.json", "package-lock.json"}
JS_IDENT_START = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_$")
JS_IDENT_CONT = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789$")


@dataclass(frozen=True)
class RepoConfig:
    key: str
    path: Path
    edition: str
    repo_kind: str


@dataclass
class GitInfo:
    branch: str = "unknown"
    commit: str = "unknown"
    short_commit: str = "unknown"
    date: str = "unknown"
    subject: str = "unknown"
    refs: str = ""
    remote: str = ""


@dataclass
class FileInfo:
    repo: str
    path: str
    bucket: str
    lines: int
    bytes: int
    indexable: bool
    skip_reason: str = ""


@dataclass
class ObjectRecord:
    repo: str
    file: str
    line: int
    object_type: str
    object_key: str
    assignment_kind: str


@dataclass
class AddCallRecord:
    repo: str
    file: str
    line: int
    function_name: str
    mapped: bool


@dataclass
class FunctionRecord:
    repo: str
    file: str
    line: int
    name: str
    kind: str


@dataclass
class ReferenceRecord:
    repo: str
    file: str
    line: int
    column: int
    context: str
    kind: str
    confidence: str


@dataclass
class SyntaxFileRecord:
    repo: str
    file: str
    markers: int
    attribute_chunks: int
    fields: list[str] = field(default_factory=list)


@dataclass
class FileDetail:
    id: str
    repo: str
    path: str
    bucket: str
    lines: int
    bytes: int
    indexable: bool
    skip_reason: str
    object_counts: dict[str, int]
    objects: list[ObjectRecord] = field(default_factory=list)
    function_objects: list[ObjectRecord] = field(default_factory=list)
    add_calls: list[AddCallRecord] = field(default_factory=list)
    functions: list[FunctionRecord] = field(default_factory=list)
    source_keys: dict[str, int] = field(default_factory=dict)
    required_versions: dict[str, int] = field(default_factory=dict)
    reference_symbols: dict[str, int] = field(default_factory=dict)
    reference_samples: list[ReferenceRecord] = field(default_factory=list)
    syntax_markers: int = 0
    syntax_attribute_chunks: int = 0
    syntax_fields: list[str] = field(default_factory=list)
    line_contexts: dict[str, str] = field(default_factory=dict)


@dataclass
class CoverageMetric:
    key: str
    label: str
    current: int
    target: int
    missed: int
    severity: str
    description: str
    action: str


@dataclass
class GraphNode:
    id: str
    label: str
    kind: str
    count: int = 0


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: str
    count: int = 1


@dataclass
class GraphView:
    key: str
    title: str
    description: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@dataclass
class AnalysisResult:
    generated_at: str
    project_root: str
    repos: dict[str, GitInfo]
    files: list[FileInfo]
    objects: list[ObjectRecord]
    function_objects: list[ObjectRecord]
    add_calls: list[AddCallRecord]
    functions: list[FunctionRecord]
    syntax_files: list[SyntaxFileRecord]
    source_keys: dict[str, int]
    required_versions: dict[str, dict[str, int]]
    references: dict[str, list[ReferenceRecord]]
    file_details: list[FileDetail]
    coverage_metrics: list[CoverageMetric]
    graph_views: list[GraphView]
    current_object_count: int
    robust_object_count: int
    current_add_count: int
    robust_add_count: int


BRACKET_OBJECT = re.compile(r"""(?m)^\s*(\w+)\s*\[\s*(["'])(.*?)\2\s*\]\s*=\s*\{""")
DOT_OBJECT = re.compile(r"""(?m)^\s*(\w+)\.([A-Za-z_$][\w$]*)\s*=\s*\{""")
FUNCTION_OBJECT = re.compile(
    r"""(?m)^\s*(\w+)\s*\[\s*(["'])(.*?)\2\s*\]\s*=\s*function\s*\("""
)
CURRENT_BRACKET_OBJECT = re.compile(
    r"""(?m)^(\w+)\s*\[\s*["']([^"']+)["']\s*\]\s*=\s*\{"""
)
CURRENT_DOT_OBJECT = re.compile(r"""(?m)^(\w+)\.(\w+)\s*=\s*\{""")
ADD_CALL = re.compile(r"""(?m)^\s*(Add[A-Za-z_$][\w$]*)\s*\(""")
CURRENT_ADD_CALL = re.compile(r"""(?m)^(Add\w+)\s*\(""")
FUNCTION_DECL = re.compile(r"""(?m)^function\s+([A-Za-z_$][\w$]*)\s*\(""")
FUNCTION_VAR = re.compile(
    r"""(?m)^\s*(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*function\s*\("""
)
FUNCTION_ASSIGN = re.compile(r"""(?m)^\s*([A-Za-z_$][\w$]*)\s*=\s*function\s*\(""")
REQUIRED_VERSION = re.compile(r"""RequiredSheetVersion\(([^)]*)\)""")
SOURCE_REF = re.compile(r"""\[\s*["']([^"']+)["']\s*,\s*(?:\d+|["'])""")
ATTRIBUTE_BLOCK = re.compile(
    r"""(?m)^\t*(\w+)\s*:\s*(.+?)(?:,\s*)?$\s*(/\*[\s\S]*?\*/)"""
)
FIELD_LINE = re.compile(r"""(?m)^\t*([A-Za-z_$][\w$]*)\s*:""")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze local MPMB source repositories and render an HTML report."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root containing data/ and scripts/.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("scripts/analyze/reports/mpmb-analysis.html"),
        help="HTML report output path.",
    )
    parser.add_argument(
        "--json-output", type=Path, default=None, help="Optional JSON output path."
    )
    args = parser.parse_args()

    root = args.root.resolve()
    output = resolve_output(root, args.output)
    json_output = (
        resolve_output(root, args.json_output)
        if args.json_output
        else output.with_suffix(".json")
    )

    result = analyze(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(result), encoding="utf-8")
    json_output.write_text(to_json(result), encoding="utf-8")

    print(f"HTML report: {output}")
    print(f"JSON report: {json_output}")
    print(f"Selected JS files: {sum(1 for f in result.files if f.indexable)}")
    print(f"Robust object literals: {result.robust_object_count}")
    print(f"Function symbols with references: {len(result.references)}")
    return 0


def resolve_output(root: Path, output: Path | None) -> Path:
    if output is None:
        return root / "scripts/analyze/reports/mpmb-analysis.json"
    return output if output.is_absolute() else root / output


def analyze(root: Path) -> AnalysisResult:
    configs = [
        RepoConfig("mpmb_source", root / "data/mpmb_source", "2014", "mpmb"),
        RepoConfig("mpmb_source_2024", root / "data/mpmb_source_2024", "2024", "mpmb"),
        RepoConfig("imports_source", root / "data/imports_source", "auto", "imports"),
    ]

    repos = {cfg.key: git_info(cfg.path) for cfg in configs}
    files: list[FileInfo] = []
    objects: list[ObjectRecord] = []
    function_objects: list[ObjectRecord] = []
    add_calls: list[AddCallRecord] = []
    functions: list[FunctionRecord] = []
    syntax_files: list[SyntaxFileRecord] = []
    source_keys: Counter[str] = Counter()
    required_versions: dict[str, Counter[str]] = {cfg.key: Counter() for cfg in configs}
    selected_texts: list[tuple[RepoConfig, Path, str, list[int]]] = []
    text_by_file: dict[tuple[str, str], str] = {}
    file_source_keys: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    file_required_versions: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    object_miss_breakdown: Counter[str] = Counter()

    current_object_count = 0
    current_add_count = 0

    for cfg in configs:
        for path in iter_js_files(cfg.path):
            text = read_text(path)
            rel_path = rel(cfg.path, path)
            line_starts = compute_line_starts(text)
            indexable, skip_reason = indexable_status(path)
            files.append(
                FileInfo(
                    repo=cfg.key,
                    path=rel_path,
                    bucket=bucket_for(cfg.path, path),
                    lines=text.count("\n") + (1 if text else 0),
                    bytes=path.stat().st_size,
                    indexable=indexable,
                    skip_reason=skip_reason,
                )
            )

            if not indexable:
                continue

            selected_texts.append((cfg, path, text, line_starts))
            text_by_file[(cfg.key, rel_path)] = text

            current_object_count += count_current_objects(text)
            current_add_count += count_current_adds(text)
            object_miss_breakdown.update(classify_object_misses(text))
            objects.extend(extract_objects(cfg, cfg.path, path, text, line_starts))
            function_objects.extend(
                extract_function_objects(cfg, cfg.path, path, text, line_starts)
            )
            add_calls.extend(extract_add_calls(cfg, cfg.path, path, text, line_starts))
            functions.extend(extract_functions(cfg, cfg.path, path, text, line_starts))

            for version in REQUIRED_VERSION.findall(text):
                version_key = version.strip()
                required_versions[cfg.key][version_key] += 1
                file_required_versions[(cfg.key, rel_path)][version_key] += 1
            for key in SOURCE_REF.findall(text):
                if looks_like_source_key(key):
                    source_keys[key] += 1
                    file_source_keys[(cfg.key, rel_path)][key] += 1

            if rel_path.startswith("additional content syntax/"):
                syntax_files.append(extract_syntax_file(cfg, cfg.path, path, text))

    symbols = build_reference_symbols(functions)
    references = extract_references(selected_texts, symbols)
    file_details = build_file_details(
        files,
        objects,
        function_objects,
        add_calls,
        functions,
        syntax_files,
        references,
        file_source_keys,
        file_required_versions,
        text_by_file,
    )
    coverage_metrics = build_coverage_metrics(
        current_object_count,
        len(objects),
        current_add_count,
        sum(1 for call in add_calls if call.mapped),
        object_miss_breakdown,
        function_objects,
        functions,
        syntax_files,
    )
    graph_views = build_graph_views(file_details, objects, add_calls)

    return AnalysisResult(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        project_root=str(root),
        repos=repos,
        files=files,
        objects=objects,
        function_objects=function_objects,
        add_calls=add_calls,
        functions=functions,
        syntax_files=syntax_files,
        source_keys=dict(source_keys.most_common()),
        required_versions={
            key: dict(counter.most_common())
            for key, counter in required_versions.items()
        },
        references=references,
        file_details=file_details,
        coverage_metrics=coverage_metrics,
        graph_views=graph_views,
        current_object_count=current_object_count,
        robust_object_count=len(objects),
        current_add_count=current_add_count,
        robust_add_count=sum(1 for call in add_calls if call.mapped),
    )


def git_info(path: Path) -> GitInfo:
    return GitInfo(
        branch=git(path, "rev-parse", "--abbrev-ref", "HEAD"),
        commit=git(path, "rev-parse", "HEAD"),
        short_commit=git(path, "rev-parse", "--short", "HEAD"),
        date=git(path, "log", "-1", "--format=%cs"),
        subject=git(path, "log", "-1", "--format=%s"),
        refs=git(path, "log", "-1", "--format=%D"),
        remote=git(path, "remote", "get-url", "origin"),
    )


def git(path: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), *args],
            encoding="utf-8",
            errors="replace",
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def iter_js_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*.js")
        if path.is_file()
        and ".git" not in path.parts
        and "node_modules" not in path.parts
    )


def read_text(path: Path) -> str:
    return (
        path.read_text(encoding="utf-8", errors="ignore")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def rel(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def indexable_status(path: Path) -> tuple[bool, str]:
    name = path.name
    if name in SKIP_NAMES:
        return False, name
    if name.startswith("all_WotC_"):
        return False, "generated aggregate bundle"
    if name.endswith(".min.js"):
        return False, "minified generated bundle"
    return True, ""


def bucket_for(root: Path, path: Path) -> str:
    parts = path.relative_to(root).parts
    if not parts:
        return "(root)"
    first = parts[0]
    if first in {
        "_functions",
        "_variables",
        "additional content",
        "additional content syntax",
        "Homebrew",
        "WotC 2024",
    }:
        return first
    if first == "WotC material":
        name = path.name
        if name.startswith("pub_"):
            return "WotC material/pub"
        if name.startswith("ua_"):
            return "WotC material/ua"
        if name.startswith("ps_"):
            return "WotC material/ps"
        if name.startswith("wip_"):
            return "WotC material/wip"
        if name.startswith("all_WotC_") or name.endswith(".min.js"):
            return "WotC material/generated"
        return "WotC material/other"
    return first


def compute_line_starts(text: str) -> list[int]:
    starts = [0]
    starts.extend(match.end() for match in re.finditer("\n", text))
    return starts


def line_col(line_starts: list[int], pos: int) -> tuple[int, int]:
    lo = 0
    hi = len(line_starts)
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if line_starts[mid] <= pos:
            lo = mid
        else:
            hi = mid
    return lo + 1, pos - line_starts[lo] + 1


def line_context(text: str, line: int) -> str:
    lines = text.splitlines()
    if 1 <= line <= len(lines):
        return lines[line - 1].strip()
    return ""


def count_current_objects(text: str) -> int:
    total = 0
    for match in CURRENT_BRACKET_OBJECT.finditer(text):
        if match.group(1) in OBJECT_TYPES:
            total += 1
    for match in CURRENT_DOT_OBJECT.finditer(text):
        if match.group(1) in OBJECT_TYPES:
            total += 1
    return total


def classify_object_misses(text: str) -> Counter[str]:
    """Bucket robust object assignments that the legacy baseline patterns miss."""
    current_starts: set[int] = set()
    for match in CURRENT_BRACKET_OBJECT.finditer(text):
        if match.group(1) in OBJECT_TYPES:
            current_starts.add(match.start())
    for match in CURRENT_DOT_OBJECT.finditer(text):
        if match.group(1) in OBJECT_TYPES:
            current_starts.add(match.start())

    buckets: Counter[str] = Counter()
    robust_seen: set[int] = set()
    for kind, pattern in (
        ("bracket_object", BRACKET_OBJECT),
        ("dot_object", DOT_OBJECT),
    ):
        for match in pattern.finditer(text):
            if match.group(1) not in OBJECT_TYPES or match.start() in robust_seen:
                continue
            robust_seen.add(match.start())
            if match.start() in current_starts:
                continue
            line_prefix = text[match.start() : match.start(1)]
            had_reason = False
            if line_prefix and line_prefix.isspace():
                buckets["indented_object_assignment"] += 1
                had_reason = True
            if kind == "bracket_object" and "'" in match.group(3):
                buckets["apostrophe_key"] += 1
                had_reason = True
            if not had_reason:
                buckets["other_object_assignment"] += 1
    for start in current_starts - robust_seen:
        buckets["legacy_only_object_assignment"] += 1
    return buckets


def count_current_adds(text: str) -> int:
    return sum(
        1
        for match in CURRENT_ADD_CALL.finditer(text)
        if match.group(1) in ADD_DECLARATIONS
    )


def extract_objects(
    cfg: RepoConfig, root: Path, path: Path, text: str, starts: list[int]
) -> list[ObjectRecord]:
    records: list[ObjectRecord] = []
    for match in BRACKET_OBJECT.finditer(text):
        object_type = match.group(1)
        if object_type not in OBJECT_TYPES:
            continue
        line, _ = line_col(starts, match.start())
        records.append(
            ObjectRecord(
                cfg.key,
                rel(root, path),
                line,
                object_type,
                match.group(3),
                "bracket_object",
            )
        )
    for match in DOT_OBJECT.finditer(text):
        object_type = match.group(1)
        if object_type not in OBJECT_TYPES:
            continue
        line, _ = line_col(starts, match.start())
        records.append(
            ObjectRecord(
                cfg.key,
                rel(root, path),
                line,
                object_type,
                match.group(2),
                "dot_object",
            )
        )
    return records


def extract_function_objects(
    cfg: RepoConfig, root: Path, path: Path, text: str, starts: list[int]
) -> list[ObjectRecord]:
    records: list[ObjectRecord] = []
    for match in FUNCTION_OBJECT.finditer(text):
        object_type = match.group(1)
        if object_type not in OBJECT_TYPES:
            continue
        line, _ = line_col(starts, match.start())
        records.append(
            ObjectRecord(
                cfg.key,
                rel(root, path),
                line,
                object_type,
                match.group(3),
                "function_object",
            )
        )
    return records


def extract_add_calls(
    cfg: RepoConfig, root: Path, path: Path, text: str, starts: list[int]
) -> list[AddCallRecord]:
    records: list[AddCallRecord] = []
    for match in ADD_CALL.finditer(text):
        name = match.group(1)
        line, _ = line_col(starts, match.start())
        records.append(
            AddCallRecord(
                cfg.key, rel(root, path), line, name, name in ADD_DECLARATIONS
            )
        )
    return records


def extract_functions(
    cfg: RepoConfig, root: Path, path: Path, text: str, starts: list[int]
) -> list[FunctionRecord]:
    records: list[FunctionRecord] = []
    if not rel(root, path).startswith("_functions/"):
        return records
    seen: set[tuple[int, str]] = set()
    for kind, pattern in (
        ("declaration", FUNCTION_DECL),
        ("var_function", FUNCTION_VAR),
        ("assignment_function", FUNCTION_ASSIGN),
    ):
        for match in pattern.finditer(text):
            name = match.group(1)
            key = (match.start(), name)
            if key in seen:
                continue
            seen.add(key)
            line, _ = line_col(starts, match.start())
            records.append(FunctionRecord(cfg.key, rel(root, path), line, name, kind))
    return records


def extract_syntax_file(
    cfg: RepoConfig, root: Path, path: Path, text: str
) -> SyntaxFileRecord:
    markers = len(re.findall(r"//\s*(?:REQUIRED|OPTIONAL)\s*//", text))
    attrs = [
        match.group(1)
        for match in ATTRIBUTE_BLOCK.finditer(text)
        if "// REQUIRED //" in match.group(3) or "// OPTIONAL //" in match.group(3)
    ]
    fields = sorted(set(FIELD_LINE.findall(text)))
    return SyntaxFileRecord(cfg.key, rel(root, path), markers, len(attrs), fields)


def looks_like_source_key(key: str) -> bool:
    if len(key) > 20:
        return False
    if key.lower() in {
        "action",
        "bonus action",
        "reaction",
        "darkvision",
        "common",
        "bard",
        "druid",
        "sorcerer",
        "wizard",
        "cleric",
        "warlock",
        "fighter",
        "ranger",
        "rogue",
        "monk",
        "paladin",
        "barbarian",
    }:
        return False
    return any(ch.isupper() or ch.isdigit() or ch in ":.-" for ch in key)


def build_reference_symbols(functions: list[FunctionRecord]) -> set[str]:
    symbols = {record.name for record in functions}
    symbols.update(OBJECT_TYPES)
    symbols.update(ADD_DECLARATIONS)
    return {symbol for symbol in symbols if symbol}


def extract_references(
    selected_texts: list[tuple[RepoConfig, Path, str, list[int]]],
    symbols: set[str],
) -> dict[str, list[ReferenceRecord]]:
    references: dict[str, list[ReferenceRecord]] = {symbol: [] for symbol in symbols}
    for cfg, path, text, starts in selected_texts:
        root = cfg.path
        for ident, pos in iter_identifiers(text):
            if ident not in symbols:
                continue
            line, col = line_col(starts, pos)
            kind, confidence = classify_identifier_reference(ident, text, pos)
            references[ident].append(
                ReferenceRecord(
                    cfg.key,
                    rel(root, path),
                    line,
                    col,
                    line_context(text, line),
                    kind,
                    confidence,
                )
            )
        for ident, pos in iter_string_mentions(text, symbols):
            line, col = line_col(starts, pos)
            references[ident].append(
                ReferenceRecord(
                    cfg.key,
                    rel(root, path),
                    line,
                    col,
                    line_context(text, line),
                    "string_mention",
                    "string_mention",
                )
            )
    return {key: refs for key, refs in sorted(references.items()) if refs}


def classify_identifier_reference(symbol: str, text: str, pos: int) -> tuple[str, str]:
    after = skip_space(text, pos + len(symbol))
    before = prev_non_space(text, pos)
    next_char = text[after] if after < len(text) else ""
    prev_char = text[before] if before >= 0 else ""
    if next_char == "(":
        return "call", "function_call"
    if symbol in OBJECT_TYPES and next_char in {"[", "."}:
        return "registry_access", "object_registry_access"
    if symbol in ADD_DECLARATIONS:
        return "add_symbol", "exact_identifier"
    if prev_char in {"[", ".", "(", ",", "=", ":", ";", "{", "}"}:
        return "identifier", "exact_identifier"
    return "identifier", "likely_dynamic_reference"


def skip_space(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def prev_non_space(text: str, pos: int) -> int:
    pos -= 1
    while pos >= 0 and text[pos].isspace():
        pos -= 1
    return pos


def iter_string_mentions(text: str, symbols: set[str]) -> Iterable[tuple[str, int]]:
    if not symbols:
        return
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            i += 2
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if ch in {"'", '"', "`"}:
            quote = ch
            literal_start = i + 1
            i += 1
            literal_parts: list[tuple[str, int]] = []
            chunk_start = literal_start
            chunk_chars: list[str] = []
            while i < n:
                if text[i] == "\\":
                    if i + 1 < n:
                        chunk_chars.append(text[i + 1])
                    i += 2
                    continue
                if text[i] == quote:
                    literal_parts.append(("".join(chunk_chars), chunk_start))
                    i += 1
                    break
                chunk_chars.append(text[i])
                i += 1
            else:
                literal_parts.append(("".join(chunk_chars), chunk_start))
            for chunk, offset in literal_parts:
                for match in re.finditer(r"[A-Za-z_$][\w$]*", chunk):
                    ident = match.group(0)
                    if ident in symbols:
                        yield ident, offset + match.start()
            continue
        i += 1


def iter_identifiers(text: str) -> Iterable[tuple[str, int]]:
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if ch == "/" and nxt == "/":
            i += 2
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if ch in {"'", '"', "`"}:
            quote = ch
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if ch == "/" and looks_like_regex_start(text, i):
            i += 1
            in_class = False
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == "[":
                    in_class = True
                elif text[i] == "]":
                    in_class = False
                elif text[i] == "/" and not in_class:
                    i += 1
                    while i < n and text[i].isalpha():
                        i += 1
                    break
                i += 1
            continue
        if ch in JS_IDENT_START:
            start = i
            i += 1
            while i < n and text[i] in JS_IDENT_CONT:
                i += 1
            yield text[start:i], start
            continue
        i += 1


def looks_like_regex_start(text: str, pos: int) -> bool:
    prefix = text[max(0, pos - 20) : pos].rstrip()
    if not prefix:
        return True
    return prefix[-1] in "=(:,![{;?&|\n"


def build_file_details(
    files: list[FileInfo],
    objects: list[ObjectRecord],
    function_objects: list[ObjectRecord],
    add_calls: list[AddCallRecord],
    functions: list[FunctionRecord],
    syntax_files: list[SyntaxFileRecord],
    references: dict[str, list[ReferenceRecord]],
    file_source_keys: dict[tuple[str, str], Counter[str]],
    file_required_versions: dict[tuple[str, str], Counter[str]],
    text_by_file: dict[tuple[str, str], str],
) -> list[FileDetail]:
    details: dict[tuple[str, str], FileDetail] = {}
    touched_lines: dict[tuple[str, str], set[int]] = defaultdict(set)

    for file in files:
        key = (file.repo, file.path)
        details[key] = FileDetail(
            id=file_id(file.repo, file.path),
            repo=file.repo,
            path=file.path,
            bucket=file.bucket,
            lines=file.lines,
            bytes=file.bytes,
            indexable=file.indexable,
            skip_reason=file.skip_reason,
            object_counts={},
            source_keys=dict(file_source_keys.get(key, Counter()).most_common()),
            required_versions=dict(
                file_required_versions.get(key, Counter()).most_common()
            ),
        )

    for record in objects:
        key = (record.repo, record.file)
        detail = details.get(key)
        if not detail:
            continue
        detail.objects.append(record)
        detail.object_counts[record.object_type] = (
            detail.object_counts.get(record.object_type, 0) + 1
        )
        touched_lines[key].add(record.line)

    for record in function_objects:
        key = (record.repo, record.file)
        detail = details.get(key)
        if not detail:
            continue
        detail.function_objects.append(record)
        touched_lines[key].add(record.line)

    for record in add_calls:
        key = (record.repo, record.file)
        detail = details.get(key)
        if not detail:
            continue
        detail.add_calls.append(record)
        touched_lines[key].add(record.line)

    for record in functions:
        key = (record.repo, record.file)
        detail = details.get(key)
        if not detail:
            continue
        detail.functions.append(record)
        touched_lines[key].add(record.line)

    for record in syntax_files:
        key = (record.repo, record.file)
        detail = details.get(key)
        if not detail:
            continue
        detail.syntax_markers = record.markers
        detail.syntax_attribute_chunks = record.attribute_chunks
        detail.syntax_fields = record.fields

    for symbol, refs in references.items():
        for ref in refs:
            key = (ref.repo, ref.file)
            detail = details.get(key)
            if not detail:
                continue
            detail.reference_symbols[symbol] = (
                detail.reference_symbols.get(symbol, 0) + 1
            )
            if len(detail.reference_samples) < 80:
                detail.reference_samples.append(ref)
                touched_lines[key].add(ref.line)

    for detail in details.values():
        detail.object_counts = dict(Counter(detail.object_counts).most_common())
        detail.reference_symbols = dict(
            Counter(detail.reference_symbols).most_common(100)
        )
        key = (detail.repo, detail.path)
        text = text_by_file.get(key)
        if not text:
            continue
        for line in sorted(touched_lines.get(key, set())):
            detail.line_contexts[str(line)] = line_context(text, line)

    return sorted(details.values(), key=lambda item: (item.repo, item.path))


def file_id(repo: str, path: str) -> str:
    return f"{repo}:{path}"


def build_coverage_metrics(
    current_object_count: int,
    robust_object_count: int,
    current_add_count: int,
    robust_add_count: int,
    object_miss_breakdown: Counter[str],
    function_objects: list[ObjectRecord],
    functions: list[FunctionRecord],
    syntax_files: list[SyntaxFileRecord],
) -> list[CoverageMetric]:
    assignment_style_functions = sum(
        1 for record in functions if record.kind != "declaration"
    )
    syntax_marker_gap = sum(
        max(0, record.markers - record.attribute_chunks) for record in syntax_files
    )
    metrics = [
        CoverageMetric(
            "object_baseline",
            "Object assignment parser coverage",
            current_object_count,
            robust_object_count,
            max(0, robust_object_count - current_object_count),
            severity_for_gap(current_object_count, robust_object_count),
            "Compares current chunker-style object patterns with the whitespace-tolerant, quote-backref robust scanner.",
            "Use the robust bracket/dot assignment scanner as the parser target, then validate suspicious misses with an AST backend.",
        ),
        CoverageMetric(
            "add_call_baseline",
            "Mapped Add* call coverage",
            current_add_count,
            robust_add_count,
            max(0, robust_add_count - current_add_count),
            severity_for_gap(current_add_count, robust_add_count),
            "Compares line-start Add* matching with the indentation-tolerant Add declaration scan.",
            "Treat AddSubClass/AddFeatureChoice/AddBackgroundVariant and related helpers as first-class registry relationships.",
        ),
        CoverageMetric(
            "indented_object_assignment",
            "Indented object assignments",
            0,
            object_miss_breakdown.get("indented_object_assignment", 0),
            object_miss_breakdown.get("indented_object_assignment", 0),
            "high"
            if object_miss_breakdown.get("indented_object_assignment", 0)
            else "ok",
            "Object registry assignments that are structurally valid but invisible to strict column-zero patterns.",
            "Normalize leading whitespace before matching, or parse assignment expressions instead of anchoring to column zero.",
        ),
        CoverageMetric(
            "apostrophe_key",
            "Apostrophe object keys",
            0,
            object_miss_breakdown.get("apostrophe_key", 0),
            object_miss_breakdown.get("apostrophe_key", 0),
            "medium" if object_miss_breakdown.get("apostrophe_key", 0) else "ok",
            "Bracket assignments whose object key contains an apostrophe and therefore breaks quote-naive regex groups.",
            "Use quote backreferences or a JavaScript parser for computed member keys.",
        ),
        CoverageMetric(
            "legacy_only_object_assignment",
            "Legacy-only object hits",
            0,
            object_miss_breakdown.get("legacy_only_object_assignment", 0),
            object_miss_breakdown.get("legacy_only_object_assignment", 0),
            "low"
            if object_miss_breakdown.get("legacy_only_object_assignment", 0)
            else "ok",
            "Object-like matches counted by the strict baseline but not accepted by the robust registry scanner.",
            "Review these as parser disagreements; an AST backend should decide whether each hit is a valid registry assignment.",
        ),
        CoverageMetric(
            "function_valued_registry",
            "Function-valued registry entries",
            0,
            len(function_objects),
            len(function_objects),
            "medium" if function_objects else "ok",
            "Registry keys whose value is a function instead of an object literal; these are source truth even without braces.",
            "Index these as callable/object hybrid entries and retain the key, registry, file, and line.",
        ),
        CoverageMetric(
            "assignment_style_function",
            "Assignment-style engine functions",
            0,
            assignment_style_functions,
            assignment_style_functions,
            "medium" if assignment_style_functions else "ok",
            "Engine helpers declared as var/let/const function expressions or bare assignments, not only function declarations.",
            "Function symbol extraction should include declarations, variable function expressions, and assignment function expressions.",
        ),
        CoverageMetric(
            "syntax_header_not_chunked",
            "Syntax marker/header gaps",
            0,
            syntax_marker_gap,
            syntax_marker_gap,
            "medium" if syntax_marker_gap else "ok",
            "Required/optional syntax markers that are not paired with an attribute chunk by the lightweight syntax scanner.",
            "Treat syntax files as templates with marker blocks, prose headers, and field definitions, then report ambiguous blocks.",
        ),
    ]
    return metrics


def severity_for_gap(current: int, target: int) -> str:
    if target <= 0 or current >= target:
        return "ok"
    ratio = current / target
    if ratio < 0.75:
        return "high"
    if ratio < 0.95:
        return "medium"
    return "low"


def build_graph_views(
    file_details: list[FileDetail],
    objects: list[ObjectRecord],
    add_calls: list[AddCallRecord],
) -> list[GraphView]:
    return [
        build_spells_graph(file_details),
        build_addsubclass_graph(file_details),
        build_2024_feature_graph(file_details, objects),
        build_source_key_graph(file_details),
        build_file_dependency_graph(file_details, add_calls),
    ]


def build_spells_graph(file_details: list[FileDetail]) -> GraphView:
    nodes: dict[str, GraphNode] = {}
    edges: Counter[tuple[str, str, str]] = Counter()
    spell_total = 0
    source_counts: Counter[str] = Counter()
    for detail in file_details:
        count = detail.object_counts.get("SpellsList", 0)
        if not count:
            continue
        spell_total += count
        add_graph_node(nodes, f"repo:{detail.repo}", detail.repo, "repo", count)
        add_graph_node(
            nodes, "object:SpellsList", "SpellsList", "registry", spell_total
        )
        edges[(f"repo:{detail.repo}", "object:SpellsList", "defines")] += count
        for source_key, source_count in detail.source_keys.items():
            source_counts[source_key] += source_count
    add_graph_node(nodes, "object:SpellsList", "SpellsList", "registry", spell_total)
    for source_key, count in source_counts.most_common(34):
        source_id = f"source:{source_key}"
        add_graph_node(nodes, source_id, source_key, "source", count)
        edges[("object:SpellsList", source_id, "source-declares")] += count
    return make_graph_view(
        "spells_ecosystem",
        "SpellsList Ecosystem",
        "Where spell registry entries live and which source keys dominate the spell corpus.",
        nodes,
        edges,
    )


def build_addsubclass_graph(file_details: list[FileDetail]) -> GraphView:
    nodes: dict[str, GraphNode] = {}
    edges: Counter[tuple[str, str, str]] = Counter()
    file_counts: Counter[str] = Counter()
    total = 0
    for detail in file_details:
        count = sum(
            1 for call in detail.add_calls if call.function_name == "AddSubClass"
        )
        if not count:
            continue
        total += count
        add_graph_node(nodes, f"repo:{detail.repo}", detail.repo, "repo", count)
        add_graph_node(nodes, "call:AddSubClass", "AddSubClass", "add-call", total)
        edges[(f"repo:{detail.repo}", "call:AddSubClass", "calls")] += count
        file_counts[file_id(detail.repo, detail.path)] += count
    for file_key, count in file_counts.most_common(28):
        label = short_file_label(file_key.split(":", 1)[1])
        add_graph_node(nodes, f"file:{file_key}", label, "file", count)
        edges[(f"file:{file_key}", "call:AddSubClass", "calls")] += count
    return make_graph_view(
        "addsubclass_call_graph",
        "AddSubClass Call Graph",
        "Repos and high-volume files that declare subclass relationships through AddSubClass.",
        nodes,
        edges,
    )


def build_2024_feature_graph(
    file_details: list[FileDetail], objects: list[ObjectRecord]
) -> GraphView:
    nodes: dict[str, GraphNode] = {}
    edges: Counter[tuple[str, str, str]] = Counter()
    types_2014 = {
        record.object_type for record in objects if record.repo == "mpmb_source"
    }
    types_2024 = {
        record.object_type for record in objects if record.repo == "mpmb_source_2024"
    }
    feature_types = (types_2024 - types_2014) | {
        "WeaponMasteriesList",
        "DefaultEvalsList",
    }
    feature_counts: Counter[str] = Counter()
    file_counts: Counter[tuple[str, str]] = Counter()
    for detail in file_details:
        if detail.repo != "mpmb_source_2024":
            continue
        for object_type, count in detail.object_counts.items():
            if object_type in feature_types:
                feature_counts[object_type] += count
                file_counts[(detail.path, object_type)] += count
    add_graph_node(
        nodes,
        "repo:mpmb_source_2024",
        "mpmb_source_2024",
        "repo",
        sum(feature_counts.values()),
    )
    for object_type, count in feature_counts.most_common():
        object_id = f"object:{object_type}"
        add_graph_node(nodes, object_id, object_type, "registry", count)
        edges[("repo:mpmb_source_2024", object_id, "defines")] += count
    for (path, object_type), count in file_counts.most_common(32):
        file_key = file_id("mpmb_source_2024", path)
        file_node = f"file:{file_key}"
        add_graph_node(nodes, file_node, short_file_label(path), "file", count)
        edges[(file_node, f"object:{object_type}", "defines")] += count
    return make_graph_view(
        "features_2024",
        "2024-Only Feature Surface",
        "Registries and files that are unique to, or especially important for, the 2024 source tree.",
        nodes,
        edges,
    )


def build_source_key_graph(file_details: list[FileDetail]) -> GraphView:
    nodes: dict[str, GraphNode] = {}
    edges: Counter[tuple[str, str, str]] = Counter()
    repo_source_counts: Counter[tuple[str, str]] = Counter()
    for detail in file_details:
        for source_key, count in detail.source_keys.items():
            repo_source_counts[(detail.repo, source_key)] += count
    for (repo, source_key), count in repo_source_counts.most_common(70):
        repo_id = f"repo:{repo}"
        source_id = f"source:{source_key}"
        add_graph_node(nodes, repo_id, repo, "repo", count)
        add_graph_node(nodes, source_id, source_key, "source", count)
        edges[(repo_id, source_id, "source-declares")] += count
    return make_graph_view(
        "source_key_provenance",
        "Source-Key Provenance",
        "Which repo checkout declares or references each source key most heavily.",
        nodes,
        edges,
    )


def build_file_dependency_graph(
    file_details: list[FileDetail], add_calls: list[AddCallRecord]
) -> GraphView:
    nodes: dict[str, GraphNode] = {}
    edges: Counter[tuple[str, str, str]] = Counter()
    file_object_edges: Counter[tuple[str, str]] = Counter()
    file_add_edges: Counter[tuple[str, str]] = Counter()
    for detail in file_details:
        file_key = file_id(detail.repo, detail.path)
        for object_type, count in detail.object_counts.items():
            file_object_edges[(file_key, object_type)] += count
    for call in add_calls:
        if call.mapped:
            file_add_edges[(file_id(call.repo, call.file), call.function_name)] += 1
    for (file_key, object_type), count in file_object_edges.most_common(45):
        path = file_key.split(":", 1)[1]
        file_node = f"file:{file_key}"
        object_node = f"object:{object_type}"
        add_graph_node(nodes, file_node, short_file_label(path), "file", count)
        add_graph_node(nodes, object_node, object_type, "registry", count)
        edges[(file_node, object_node, "defines")] += count
    for (file_key, function_name), count in file_add_edges.most_common(25):
        path = file_key.split(":", 1)[1]
        file_node = f"file:{file_key}"
        call_node = f"call:{function_name}"
        add_graph_node(nodes, file_node, short_file_label(path), "file", count)
        add_graph_node(nodes, call_node, function_name, "add-call", count)
        edges[(file_node, call_node, "calls")] += count
    return make_graph_view(
        "file_dependency_graph",
        "File Dependency Graph",
        "High-volume file-to-registry and file-to-helper relationships for parser planning.",
        nodes,
        edges,
    )


def add_graph_node(
    nodes: dict[str, GraphNode], node_id: str, label: str, kind: str, count: int = 0
) -> None:
    current = nodes.get(node_id)
    if current:
        current.count = max(current.count, count)
        return
    nodes[node_id] = GraphNode(node_id, label, kind, count)


def make_graph_view(
    key: str,
    title: str,
    description: str,
    nodes: dict[str, GraphNode],
    edges: Counter[tuple[str, str, str]],
) -> GraphView:
    edge_records = [
        GraphEdge(source, target, kind, count)
        for (source, target, kind), count in edges.most_common(90)
        if source in nodes and target in nodes
    ]
    used_nodes = {edge.source for edge in edge_records} | {
        edge.target for edge in edge_records
    }
    node_records = [node for node_id, node in nodes.items() if node_id in used_nodes]
    return GraphView(
        key,
        title,
        description,
        sorted(node_records, key=lambda item: (item.kind, item.label)),
        edge_records,
    )


def short_file_label(path: str) -> str:
    parts = path.split("/")
    if len(parts) <= 2:
        return path
    return f"{parts[-2]}/{parts[-1]}"


def to_json(result: AnalysisResult) -> str:
    return json.dumps(asdict(result), indent=2, ensure_ascii=False)


def render_html(result: AnalysisResult) -> str:
    file_counts = Counter(file.repo for file in result.files if file.indexable)
    line_counts = Counter()
    for file in result.files:
        if file.indexable:
            line_counts[file.repo] += file.lines

    object_counts = Counter(record.object_type for record in result.objects)
    add_counts = Counter(call.function_name for call in result.add_calls if call.mapped)
    all_add_counts = Counter(call.function_name for call in result.add_calls)
    function_defs = defaultdict(list)
    for record in result.functions:
        function_defs[record.name].append(record)

    top_reference_rows = sorted(
        result.references.items(), key=lambda item: len(item[1]), reverse=True
    )
    file_bucket_index = {(file.repo, file.path): file.bucket for file in result.files}
    fanout_counts = build_fanout_counts(result.references, function_defs)
    repos = sorted({file.repo for file in result.files})
    buckets = sorted({file.bucket for file in result.files if file.indexable})
    confidences = sorted(
        {ref.confidence for refs in result.references.values() for ref in refs}
    )
    payload = script_json(build_client_payload(result))

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MPMB Source Analysis</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fb;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #5d6978;
      --line: #d8dee8;
      --accent: #0f766e;
      --accent-2: #7c3aed;
      --warn: #b45309;
      --danger: #b91c1c;
      --ok: #047857;
      --soft: #edf2f7;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 14px/1.5 system-ui, -apple-system, Segoe UI, sans-serif; color: var(--ink); background: var(--bg); }}
    header {{ padding: 30px 32px 22px; background: linear-gradient(135deg, #10202f, #143634); color: white; }}
    header h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: 0; }}
    header p {{ margin: 0; color: #d7e2ee; max-width: 1100px; }}
    nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }}
    nav a {{ color: #e8fbf7; text-decoration: none; border: 1px solid rgba(255,255,255,.26); border-radius: 999px; padding: 5px 10px; font-size: 12px; }}
    main {{ padding: 24px 32px 48px; max-width: 1500px; margin: 0 auto; }}
    h2 {{ margin: 28px 0 12px; font-size: 21px; }}
    h3 {{ margin: 22px 0 10px; font-size: 16px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .card, section {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; box-shadow: 0 1px 2px rgba(20,30,40,.04); }}
    .card strong {{ display: block; font-size: 24px; color: var(--accent); }}
    .muted {{ color: var(--muted); }}
    .warn {{ color: var(--warn); }}
    table {{ width: 100%; border-collapse: collapse; background: var(--panel); }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; }}
    details {{ border: 1px solid var(--line); border-radius: 7px; background: var(--panel); margin: 8px 0; overflow: hidden; }}
    summary {{ cursor: pointer; padding: 10px 12px; font-weight: 650; }}
    details .details-body {{ padding: 0 12px 12px; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 10px 0 14px; }}
    input[type="search"], select {{ min-height: 36px; padding: 8px 10px; border: 1px solid var(--line); border-radius: 7px; background: white; }}
    input[type="search"] {{ width: min(520px, 100%); }}
    button {{ border: 1px solid var(--line); background: white; color: var(--ink); border-radius: 7px; padding: 6px 9px; cursor: pointer; }}
    button:hover {{ border-color: var(--accent); color: var(--accent); }}
    .pill {{ display: inline-block; padding: 2px 7px; border-radius: 999px; background: #e6f3f1; color: #075e56; font-size: 12px; margin-left: 6px; }}
    .pill.warn {{ background: #fef3c7; color: #92400e; }}
    .pill.high {{ background: #fee2e2; color: #991b1b; }}
    .pill.medium {{ background: #ffedd5; color: #9a3412; }}
    .pill.low {{ background: #e0f2fe; color: #075985; }}
    .pill.ok {{ background: #dcfce7; color: #166534; }}
    .scroll {{ overflow-x: auto; }}
    .context {{ color: #334155; }}
    .split {{ display: grid; grid-template-columns: minmax(280px, 370px) minmax(0, 1fr); gap: 14px; min-height: 620px; }}
    .tree-panel {{ border: 1px solid var(--line); border-radius: 8px; overflow: auto; max-height: 760px; background: #fbfcfe; padding: 10px; }}
    .detail-panel {{ border: 1px solid var(--line); border-radius: 8px; min-height: 620px; padding: 14px; overflow: auto; }}
    .tree-panel details {{ border: 0; background: transparent; margin: 0; }}
    .tree-panel summary {{ padding: 4px 2px; }}
    .file-button {{ display: block; width: 100%; border: 0; background: transparent; text-align: left; padding: 4px 6px; border-radius: 5px; color: #243447; }}
    .file-button:hover, .file-button.active {{ background: #e6f3f1; color: #075e56; }}
    .mini-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; margin: 10px 0 14px; }}
    .mini-card {{ background: var(--soft); border-radius: 7px; padding: 10px; }}
    .mini-card strong {{ display: block; font-size: 18px; color: var(--accent); }}
    .metric {{ display: grid; grid-template-columns: minmax(210px, 1fr) 2fr minmax(130px, auto); gap: 10px; align-items: center; }}
    .bar {{ height: 10px; border-radius: 999px; background: #e5e7eb; overflow: hidden; }}
    .bar span {{ display: block; height: 100%; background: var(--accent); }}
    .graph-shell {{ border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: #fbfcfe; }}
    #graphSvg {{ width: 100%; min-height: 540px; display: block; }}
    .node-label {{ font: 12px system-ui, -apple-system, Segoe UI, sans-serif; fill: #1f2937; }}
    .edge-label {{ font: 10px system-ui, -apple-system, Segoe UI, sans-serif; fill: #64748b; }}
    .copy-row {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .reference-file {{ background: #fbfcfe; }}
    @media (max-width: 900px) {{
      main {{ padding: 18px; }}
      .split {{ grid-template-columns: 1fr; }}
      .tree-panel {{ max-height: 420px; }}
      .metric {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>MPMB Source Analysis</h1>
    <p>Generated {esc(result.generated_at)} from {esc(result.project_root)}. This standalone source intelligence report is for MPMB maintainers, contributors, and MPMB-Copilot agents: what exists, where it lives, how it connects, and where extraction still has blind spots.</p>
    <nav>
      <a href="#file-explorer">File Explorer</a>
      <a href="#coverage">Coverage</a>
      <a href="#graph">Graph</a>
      <a href="#references">References</a>
      <a href="#registries">Registries</a>
      <a href="#provenance">Provenance</a>
    </nav>
  </header>
  <main>
    <div class="grid">
      <div class="card"><span class="muted">Selected JS Files</span><strong>{sum(file_counts.values()):,}</strong></div>
      <div class="card"><span class="muted">Selected Lines</span><strong>{sum(line_counts.values()):,}</strong></div>
      <div class="card"><span class="muted">Robust Object Literals</span><strong>{result.robust_object_count:,}</strong></div>
      <div class="card"><span class="muted">Function Symbols Referenced</span><strong>{len(result.references):,}</strong></div>
    </div>

    <h2 id="file-explorer">Interactive File Explorer</h2>
    <section>
      <p class="muted">Browse repo → folder → file. The detail panel shows parser-relevant facts, source keys, syntax fields, references, line context, and reproducible search commands.</p>
      <div class="toolbar">
        <input id="fileSearch" type="search" placeholder="Filter files, functions, object keys, source keys">
        <select id="fileRepoFilter"><option value="">All repos</option>{options(repos)}</select>
      </div>
      <div class="split">
        <div id="fileTree" class="tree-panel"></div>
        <div id="fileDetail" class="detail-panel"></div>
      </div>
    </section>

    <h2 id="coverage">Coverage Dashboard</h2>
    <section>
      <p class="muted">The goal is not just a pretty count. These are parser-development targets: what the current baseline catches, what the robust scanner sees, and why misses happen.</p>
      {coverage_dashboard(result.coverage_metrics)}
    </section>

    <h2 id="graph">Visual Graph</h2>
    <section>
      <div class="toolbar">
        <select id="graphSelect">{graph_options(result.graph_views)}</select>
        <span id="graphDescription" class="muted"></span>
      </div>
      <div class="graph-shell"><svg id="graphSvg" role="img" aria-label="MPMB source relationship graph"></svg></div>
    </section>

    <h2 id="provenance">Repository Provenance</h2>
    <section class="scroll">{repo_table(result)}</section>

    <h2>Inventory</h2>
    <section class="scroll">{inventory_table(result.files)}</section>

    <h2>Parser Baseline Counts</h2>
    <div class="grid">
      <div class="card"><span class="muted">Current Object Baseline</span><strong>{result.current_object_count:,}</strong><span class="muted">Matches current chunker-style patterns.</span></div>
      <div class="card"><span class="muted">Robust Object Target</span><strong>{result.robust_object_count:,}</strong><span class="muted">Allows whitespace, dot assignments, quote backrefs.</span></div>
      <div class="card"><span class="muted">Current Add Baseline</span><strong>{result.current_add_count:,}</strong></div>
      <div class="card"><span class="muted">Robust Add Target</span><strong>{result.robust_add_count:,}</strong></div>
    </div>

    <h2 id="registries">Object Registries</h2>
    <section class="scroll">{counter_table(object_counts, "Object type", "Count")}</section>

    <h2>Mapped Add Calls</h2>
    <section class="scroll">{counter_table(add_counts, "Function", "Mapped count")}</section>

    <h2>All Add-like Calls</h2>
    <section class="scroll">{counter_table(all_add_counts, "Function", "Count")}</section>

    <h2>Function-valued Registry Entries</h2>
    <section class="scroll">{object_record_table(result.function_objects)}</section>

    <h2>Syntax Templates</h2>
    <section class="scroll">{syntax_table(result.syntax_files)}</section>

    <h2>Source Keys</h2>
    <section class="scroll">{dict_table(result.source_keys, "Source key", "References", limit=120)}</section>

    <h2>Required Sheet Versions</h2>
    <section>{required_versions(result.required_versions)}</section>

    <h2 id="references">Function Reference Explorer</h2>
    <section>
      <p class="muted">References are grouped by file, definitions are kept separate, and confidence badges distinguish calls, registry access, exact identifiers, dynamic-looking mentions, and string mentions.</p>
      <div class="toolbar">
        <input id="symbolSearch" type="search" placeholder="Filter symbols, e.g. AddSubClass, What, WeaponMasteriesList">
        <select id="symbolRepoFilter"><option value="">All repos</option>{options(repos)}</select>
        <select id="symbolBucketFilter"><option value="">All buckets</option>{options(buckets)}</select>
        <select id="symbolConfidenceFilter"><option value="">All confidence</option>{options(confidences)}</select>
      </div>
      <div id="symbols">{reference_details(top_reference_rows, function_defs, fanout_counts, file_bucket_index)}</div>
    </section>

    <h2>Accuracy Mode Roadmap</h2>
    <section>
      {accuracy_mode_section(result.coverage_metrics)}
    </section>
  </main>
  <script>
    const REPORT_DATA = {payload};
    {client_script()}
  </script>
</body>
</html>"""


def build_fanout_counts(
    references: dict[str, list[ReferenceRecord]],
    function_defs: dict[str, list[FunctionRecord]],
) -> dict[str, int]:
    file_symbols: dict[tuple[str, str], set[str]] = defaultdict(set)
    for symbol, refs in references.items():
        for ref in refs:
            file_symbols[(ref.repo, ref.file)].add(symbol)

    fanout: dict[str, int] = {}
    for symbol, defs in function_defs.items():
        symbols: set[str] = set()
        for definition in defs:
            symbols.update(file_symbols.get((definition.repo, definition.file), set()))
        symbols.discard(symbol)
        fanout[symbol] = len(symbols)
    return fanout


def build_client_payload(result: AnalysisResult) -> dict[str, object]:
    return {
        "files": [asdict(detail) for detail in result.file_details],
        "graphs": [asdict(view) for view in result.graph_views],
        "coverageMetrics": [asdict(metric) for metric in result.coverage_metrics],
    }


def script_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )


def options(values: Iterable[str]) -> str:
    return "".join(
        f"<option value='{esc(value)}'>{esc(value)}</option>" for value in values
    )


def graph_options(views: list[GraphView]) -> str:
    return "".join(
        f"<option value='{esc(view.key)}'>{esc(view.title)}</option>" for view in views
    )


def coverage_dashboard(metrics: list[CoverageMetric]) -> str:
    rows = []
    for metric in metrics:
        percent = coverage_percent(metric.current, metric.target)
        rows.append(
            "<tr>"
            f"<td><strong>{esc(metric.label)}</strong><br><span class='muted'>{esc(metric.description)}</span></td>"
            f"<td><div class='bar'><span style='width:{percent:.1f}%'></span></div><code>{metric.current:,} / {metric.target:,}</code></td>"
            f"<td><span class='pill {esc(metric.severity)}'>{esc(metric.severity)}</span></td>"
            f"<td>{metric.missed:,}</td>"
            f"<td>{esc(metric.action)}</td>"
            "</tr>"
        )
    return (
        "<div class='scroll'><table><thead><tr><th>Target</th><th>Current vs Target</th><th>Severity</th><th>Count</th><th>Parser Action</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def coverage_percent(current: int, target: int) -> float:
    if target <= 0:
        return 100.0
    return min(100.0, max(0.0, (current / target) * 100))


def accuracy_mode_section(metrics: list[CoverageMetric]) -> str:
    warnings = [metric for metric in metrics if metric.missed > 0]
    warning_rows = []
    for metric in warnings:
        warning_rows.append(
            "<tr>"
            f"<td><span class='pill {esc(metric.severity)}'>{esc(metric.severity)}</span></td>"
            f"<td><strong>{esc(metric.label)}</strong></td>"
            f"<td>{metric.missed:,}</td>"
            f"<td>{esc(metric.action)}</td>"
            "</tr>"
        )
    warning_table = (
        "<table><thead><tr><th>Severity</th><th>Mismatch</th><th>Count</th><th>Next Check</th></tr></thead><tbody>"
        + "".join(warning_rows)
        + "</tbody></table>"
        if warning_rows
        else "<p class='muted'>No parser mismatches found by the current checker set.</p>"
    )
    return (
        "<div class='grid'>"
        "<div class='card'><span class='muted'>Engine 1</span><strong>Baseline regex</strong><span class='muted'>Mirrors strict current chunker patterns for regression comparison.</span></div>"
        "<div class='card'><span class='muted'>Engine 2</span><strong>Brace-aware scanner</strong><span class='muted'>Whitespace-tolerant registry, Add call, syntax, and identifier scan used by this report.</span></div>"
        "<div class='card'><span class='muted'>Engine 3</span><strong>AST parser later</strong><span class='muted'>Tree-sitter or Acorn can become the tie-breaker. Any mismatch becomes a report warning.</span></div>"
        "</div>"
        "<h3>Current Mismatch Warnings</h3>"
        f"{warning_table}"
    )


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def repo_table(result: AnalysisResult) -> str:
    rows = []
    for key, info in result.repos.items():
        rows.append(
            "<tr>"
            f"<td><code>{esc(key)}</code></td>"
            f"<td>{esc(info.branch)}</td>"
            f"<td><code>{esc(info.short_commit)}</code></td>"
            f"<td>{esc(info.date)}</td>"
            f"<td>{esc(info.subject)}</td>"
            f"<td><code>{esc(info.remote)}</code></td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Repo</th><th>Branch</th><th>Commit</th><th>Date</th><th>Subject</th><th>Remote</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def inventory_table(files: list[FileInfo]) -> str:
    counts: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    for file in files:
        entry = counts[(file.repo, file.bucket)]
        entry[0] += 1
        entry[1] += file.lines
        if file.indexable:
            entry[2] += 1
    rows = []
    for (repo, bucket), (file_count, line_count, indexable_count) in sorted(
        counts.items()
    ):
        rows.append(
            f"<tr><td><code>{esc(repo)}</code></td><td>{esc(bucket)}</td><td>{file_count:,}</td><td>{indexable_count:,}</td><td>{line_count:,}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Repo</th><th>Bucket</th><th>Files</th><th>Indexable</th><th>Lines</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def counter_table(
    counter: Counter[str], name_header: str, count_header: str, limit: int | None = None
) -> str:
    rows = []
    items = counter.most_common(limit)
    for key, count in items:
        rows.append(f"<tr><td><code>{esc(key)}</code></td><td>{count:,}</td></tr>")
    return f"<table><thead><tr><th>{esc(name_header)}</th><th>{esc(count_header)}</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"


def dict_table(
    data: dict[str, int], name_header: str, count_header: str, limit: int | None = None
) -> str:
    return counter_table(Counter(data), name_header, count_header, limit=limit)


def object_record_table(records: list[ObjectRecord]) -> str:
    if not records:
        return "<p class='muted'>No records found.</p>"
    rows = []
    for record in records:
        rows.append(
            "<tr>"
            f"<td><code>{esc(record.object_type)}</code></td>"
            f"<td><code>{esc(record.object_key)}</code></td>"
            f"<td>{esc(record.repo)}</td>"
            f"<td><code>{esc(record.file)}:{record.line}</code></td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Object type</th><th>Key</th><th>Repo</th><th>Location</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def syntax_table(records: list[SyntaxFileRecord]) -> str:
    rows = []
    for record in sorted(records, key=lambda r: (r.file, r.repo)):
        rows.append(
            "<tr>"
            f"<td>{esc(record.repo)}</td>"
            f"<td><code>{esc(record.file)}</code></td>"
            f"<td>{record.markers:,}</td>"
            f"<td>{record.attribute_chunks:,}</td>"
            f"<td>{esc(', '.join(record.fields[:18]))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Repo</th><th>File</th><th>Required/Optional Markers</th><th>Attribute Chunks</th><th>Fields Sample</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def required_versions(data: dict[str, dict[str, int]]) -> str:
    blocks = []
    for repo, versions in data.items():
        blocks.append(
            f"<h3><code>{esc(repo)}</code></h3>{dict_table(versions, 'RequiredSheetVersion', 'Count', limit=30)}"
        )
    return "".join(blocks)


def reference_details(
    reference_rows: list[tuple[str, list[ReferenceRecord]]],
    function_defs: dict[str, list[FunctionRecord]],
    fanout_counts: dict[str, int],
    file_bucket_index: dict[tuple[str, str], str],
) -> str:
    blocks = []
    for symbol, refs in reference_rows:
        defs = function_defs.get(symbol, [])
        ref_files = {(ref.repo, ref.file) for ref in refs}
        repos = " ".join(
            sorted(
                {ref.repo for ref in refs} | {definition.repo for definition in defs}
            )
        )
        buckets = " ".join(
            sorted({file_bucket_index.get((ref.repo, ref.file), "") for ref in refs})
        )
        confidences = " ".join(sorted({ref.confidence for ref in refs}))
        blocks.append(
            f"<details data-symbol='{esc(symbol)}' data-repos='{esc(repos)}' data-buckets='{esc(buckets)}' data-confidences='{esc(confidences)}'>"
            f"<summary><code>{esc(symbol)}</code>"
            f"<span class='pill'>{len(refs):,} refs</span>"
            f"<span class='pill'>{len(defs):,} defs</span>"
            f"<span class='pill'>{len(ref_files):,} fan-in files</span>"
            f"<span class='pill'>{fanout_counts.get(symbol, 0):,} fan-out symbols</span></summary>"
            "<div class='details-body'>"
            f"<div class='copy-row'><button data-copy='{esc(rg_command(symbol))}'>copy all-repo rg</button><code>{esc(rg_command(symbol))}</code></div>"
            f"{definition_table(symbol, defs)}"
            f"{reference_table(symbol, refs)}"
            "</div></details>"
        )
    return "".join(blocks)


def definition_table(symbol: str, records: list[FunctionRecord]) -> str:
    if not records:
        return "<p class='muted'>No function definition recorded for this symbol.</p>"
    rows = []
    for record in records:
        command = rg_command(symbol, record.repo, record.file)
        rows.append(
            "<tr>"
            f"<td>{esc(record.repo)}</td>"
            f"<td><code>{esc(record.file)}:{record.line}</code></td>"
            f"<td>{esc(record.kind)}</td>"
            f"<td><button data-copy='{esc(command)}'>copy rg</button></td>"
            "</tr>"
        )
    return (
        "<h3>Definitions</h3><table><thead><tr><th>Repo</th><th>Location</th><th>Kind</th><th>Query</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def reference_table(symbol: str, records: list[ReferenceRecord]) -> str:
    grouped: dict[tuple[str, str], list[ReferenceRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.repo, record.file)].append(record)

    blocks = []
    for (repo, file), refs in sorted(
        grouped.items(), key=lambda item: (-len(item[1]), item[0])
    ):
        rows = []
        confidence_counts = Counter(ref.confidence for ref in refs)
        command = rg_command(symbol, repo, file)
        for record in refs:
            rows.append(
                "<tr>"
                f"<td><code>{record.line}:{record.column}</code></td>"
                f"<td><span class='pill'>{esc(record.kind)}</span><span class='pill'>{esc(record.confidence)}</span></td>"
                f"<td class='context'><code>{esc(record.context)}</code></td>"
                "</tr>"
            )
        confidence_summary = " ".join(
            f"<span class='pill'>{esc(confidence)} {count:,}</span>"
            for confidence, count in confidence_counts.most_common()
        )
        blocks.append(
            "<details class='reference-file'>"
            f"<summary><code>{esc(repo)}/{esc(file)}</code><span class='pill'>{len(refs):,} refs</span>{confidence_summary}</summary>"
            "<div class='details-body'>"
            f"<div class='copy-row'><button data-copy='{esc(command)}'>copy file rg</button><code>{esc(command)}</code></div>"
            "<table><thead><tr><th>Line</th><th>Confidence</th><th>Context</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div></details>"
        )
    return "<h3>References by File</h3>" + "".join(blocks)


def rg_command(symbol: str, repo: str | None = None, file: str | None = None) -> str:
    pattern = rf"\b{re.escape(symbol)}\b"
    if repo and file:
        return f'rg -n "{pattern}" "{repo_data_path(repo)}\\{file.replace("/", "\\")}"'
    if repo:
        return f'rg -n "{pattern}" "{repo_data_path(repo)}"'
    return (
        f'rg -n "{pattern}" '
        '"data\\mpmb_source" "data\\mpmb_source_2024" "data\\imports_source"'
    )


def repo_data_path(repo: str) -> str:
    mapping = {
        "mpmb_source": "data\\mpmb_source",
        "mpmb_source_2024": "data\\mpmb_source_2024",
        "imports_source": "data\\imports_source",
    }
    return mapping.get(repo, repo)


def client_script() -> str:
    return r"""
const state = { selectedFileId: null };

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  }[ch]));
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function fileMatches(detail, query) {
  if (!query) return true;
  const haystack = [
    detail.repo,
    detail.path,
    detail.bucket,
    ...Object.keys(detail.object_counts || {}),
    ...Object.keys(detail.source_keys || {}),
    ...Object.keys(detail.reference_symbols || {}),
    ...(detail.objects || []).map(item => item.object_key),
    ...(detail.functions || []).map(item => item.name),
    ...(detail.add_calls || []).map(item => item.function_name),
  ].join(' ').toLowerCase();
  return haystack.includes(query);
}

function buildTree(files) {
  const root = {};
  for (const detail of files) {
    const repoNode = root[detail.repo] ||= { folders: {}, files: [] };
    let node = repoNode;
    const parts = detail.path.split('/');
    for (const part of parts.slice(0, -1)) {
      node = node.folders[part] ||= { folders: {}, files: [] };
    }
    node.files.push(detail);
  }
  return root;
}

function renderFileTree() {
  const query = document.getElementById('fileSearch').value.trim().toLowerCase();
  const repoFilter = document.getElementById('fileRepoFilter').value;
  const files = REPORT_DATA.files.filter(detail =>
    (!repoFilter || detail.repo === repoFilter) && fileMatches(detail, query)
  );
  const tree = buildTree(files);
  const html = Object.entries(tree).map(([repo, node]) =>
    renderTreeNode(repo, node, true)
  ).join('');
  document.getElementById('fileTree').innerHTML = html || '<p class="muted">No matching files.</p>';
  document.querySelectorAll('[data-file-id]').forEach(button => {
    button.addEventListener('click', () => renderFileDetail(button.dataset.fileId));
    if (button.dataset.fileId === state.selectedFileId) button.classList.add('active');
  });
  if (!state.selectedFileId && files.length) renderFileDetail(files[0].id);
}

function renderTreeNode(label, node, open = false) {
  const folders = Object.entries(node.folders || {}).sort(([a], [b]) => a.localeCompare(b));
  const files = (node.files || []).sort((a, b) => a.path.localeCompare(b.path));
  const children = [
    ...folders.map(([name, child]) => renderTreeNode(name, child, false)),
    ...files.map(detail => {
      const name = detail.path.split('/').pop();
      const badges = detail.indexable ? `${formatNumber(detail.objects.length)} obj` : detail.skip_reason;
      return `<button class="file-button" data-file-id="${escapeHtml(detail.id)}">${escapeHtml(name)} <span class="muted">${escapeHtml(badges)}</span></button>`;
    })
  ].join('');
  return `<details ${open ? 'open' : ''}><summary>${escapeHtml(label)}</summary>${children}</details>`;
}

function renderFileDetail(fileId) {
  state.selectedFileId = fileId;
  const detail = REPORT_DATA.files.find(item => item.id === fileId);
  if (!detail) return;
  document.querySelectorAll('[data-file-id]').forEach(button => {
    button.classList.toggle('active', button.dataset.fileId === fileId);
  });
  const objectRows = (detail.objects || []).slice(0, 120).map(item =>
    row([code(item.object_type), code(item.object_key), lineCell(detail, item.line), copyButton(objectQuery(item))])
  ).join('');
  const functionRows = (detail.functions || []).slice(0, 120).map(item =>
    row([code(item.name), escapeHtml(item.kind), lineCell(detail, item.line), copyButton(symbolQuery(item.name, detail.repo, detail.path))])
  ).join('');
  const addRows = (detail.add_calls || []).slice(0, 120).map(item =>
    row([code(item.function_name), item.mapped ? 'mapped' : 'unmapped', lineCell(detail, item.line), copyButton(symbolQuery(item.function_name, detail.repo, detail.path))])
  ).join('');
  const sourceRows = Object.entries(detail.source_keys || {}).slice(0, 80).map(([key, count]) =>
    row([code(key), formatNumber(count), copyButton(`rg -n "${key.replaceAll('"', '\\"')}" "${repoPath(detail.repo)}\\${detail.path.replaceAll('/', '\\')}"`)])
  ).join('');
  const referenceRows = Object.entries(detail.reference_symbols || {}).slice(0, 80).map(([symbol, count]) =>
    row([code(symbol), formatNumber(count), copyButton(symbolQuery(symbol, detail.repo, detail.path))])
  ).join('');
  const sampleRows = (detail.reference_samples || []).slice(0, 50).map(item =>
    row([code(item.line + ':' + item.column), code(item.confidence), code(item.context)])
  ).join('');
  document.getElementById('fileDetail').innerHTML = `
    <h3><code>${escapeHtml(detail.repo)}/${escapeHtml(detail.path)}</code></h3>
    <div class="mini-grid">
      ${miniCard('Lines', detail.lines)}
      ${miniCard('Bytes', detail.bytes)}
      ${miniCard('Objects', (detail.objects || []).length)}
      ${miniCard('Functions', (detail.functions || []).length)}
      ${miniCard('Add Calls', (detail.add_calls || []).length)}
      ${miniCard('Source Keys', Object.keys(detail.source_keys || {}).length)}
    </div>
    <p class="muted">Bucket: <code>${escapeHtml(detail.bucket)}</code>${detail.indexable ? '' : ` • skipped: ${escapeHtml(detail.skip_reason)}`}</p>
    ${detail.syntax_markers ? `<h3>Syntax Template</h3><p>${formatNumber(detail.syntax_markers)} markers, ${formatNumber(detail.syntax_attribute_chunks)} attribute chunks</p><p class="muted">${escapeHtml((detail.syntax_fields || []).slice(0, 40).join(', '))}</p>` : ''}
    ${tableBlock('Object Entries', ['Registry', 'Key', 'Line Context', 'Query'], objectRows)}
    ${tableBlock('Function Definitions', ['Name', 'Kind', 'Line Context', 'Query'], functionRows)}
    ${tableBlock('Add Calls', ['Function', 'Mapped', 'Line Context', 'Query'], addRows)}
    ${tableBlock('Source Keys', ['Key', 'Count', 'Query'], sourceRows)}
    ${tableBlock('Reference Symbols', ['Symbol', 'Count', 'Query'], referenceRows)}
    ${tableBlock('Reference Samples', ['Line', 'Confidence', 'Context'], sampleRows)}
  `;
}

function miniCard(label, value) {
  return `<div class="mini-card"><span class="muted">${escapeHtml(label)}</span><strong>${formatNumber(value)}</strong></div>`;
}

function tableBlock(title, headers, rows) {
  if (!rows) return `<h3>${escapeHtml(title)}</h3><p class="muted">No records.</p>`;
  return `<h3>${escapeHtml(title)}</h3><div class="scroll"><table><thead><tr>${headers.map(header => `<th>${escapeHtml(header)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

function row(cells) {
  return `<tr>${cells.map(cell => `<td>${cell}</td>`).join('')}</tr>`;
}

function code(value) {
  return `<code>${escapeHtml(value)}</code>`;
}

function lineCell(detail, line) {
  return `<code>${escapeHtml(line)}: ${escapeHtml(detail.line_contexts?.[String(line)] || '')}</code>`;
}

function copyButton(command) {
  return `<button data-copy="${escapeHtml(command)}">copy rg</button>`;
}

function repoPath(repo) {
  return {
    mpmb_source: 'data\\mpmb_source',
    mpmb_source_2024: 'data\\mpmb_source_2024',
    imports_source: 'data\\imports_source',
  }[repo] || repo;
}

function symbolQuery(symbol, repo, path) {
  const escaped = symbol.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return `rg -n "\\b${escaped}\\b" "${repoPath(repo)}\\${path.replaceAll('/', '\\')}"`;
}

function objectQuery(item) {
  const key = String(item.object_key || '').replaceAll('"', '\\"');
  return `rg -n "${key}" "${repoPath(item.repo)}\\${item.file.replaceAll('/', '\\')}"`;
}

function renderGraph() {
  const select = document.getElementById('graphSelect');
  const view = REPORT_DATA.graphs.find(item => item.key === select.value) || REPORT_DATA.graphs[0];
  if (!view) return;
  document.getElementById('graphDescription').textContent = view.description;
  const svg = document.getElementById('graphSvg');
  const nodes = view.nodes || [];
  const edges = view.edges || [];
  const incoming = new Map();
  const outgoing = new Map();
  for (const node of nodes) {
    incoming.set(node.id, 0);
    outgoing.set(node.id, 0);
  }
  for (const edge of edges) {
    incoming.set(edge.target, (incoming.get(edge.target) || 0) + 1);
    outgoing.set(edge.source, (outgoing.get(edge.source) || 0) + 1);
  }
  const tiers = { left: [], middle: [], right: [] };
  for (const node of nodes) {
    if ((incoming.get(node.id) || 0) === 0) tiers.left.push(node);
    else if ((outgoing.get(node.id) || 0) === 0) tiers.right.push(node);
    else tiers.middle.push(node);
  }
  const width = 1180;
  const maxTier = Math.max(1, tiers.left.length, tiers.middle.length, tiers.right.length);
  const height = Math.max(540, maxTier * 42 + 80);
  const positions = new Map();
  placeTier(tiers.left, 120, height, positions);
  placeTier(tiers.middle, width / 2, height, positions);
  placeTier(tiers.right, width - 180, height, positions);
  const edgeSvg = edges.map(edge => {
    const a = positions.get(edge.source);
    const b = positions.get(edge.target);
    if (!a || !b) return '';
    const stroke = Math.min(6, 1 + Math.log(edge.count || 1));
    const midX = (a.x + b.x) / 2;
    const midY = (a.y + b.y) / 2;
    return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#9aa9b8" stroke-width="${stroke}" opacity="0.46"><title>${escapeHtml(edge.kind)} ${formatNumber(edge.count)}</title></line><text class="edge-label" x="${midX}" y="${midY - 3}">${formatNumber(edge.count)}</text>`;
  }).join('');
  const nodeSvg = nodes.map(node => {
    const p = positions.get(node.id);
    if (!p) return '';
    const color = nodeColor(node.kind);
    const radius = Math.min(18, 7 + Math.log((node.count || 1) + 1) * 2.2);
    const label = node.label.length > 34 ? node.label.slice(0, 31) + '...' : node.label;
    return `<g><circle cx="${p.x}" cy="${p.y}" r="${radius}" fill="${color}" opacity="0.95"><title>${escapeHtml(node.kind)}: ${escapeHtml(node.label)} (${formatNumber(node.count)})</title></circle><text class="node-label" x="${p.x + radius + 6}" y="${p.y + 4}">${escapeHtml(label)}</text></g>`;
  }).join('');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.innerHTML = edgeSvg + nodeSvg;
}

function placeTier(nodes, x, height, positions) {
  const gap = height / (nodes.length + 1);
  nodes.forEach((node, index) => positions.set(node.id, { x, y: gap * (index + 1) }));
}

function nodeColor(kind) {
  return {
    repo: '#0f766e',
    file: '#2563eb',
    registry: '#7c3aed',
    source: '#b45309',
    'add-call': '#dc2626',
  }[kind] || '#475569';
}

function applySymbolFilters() {
  const query = document.getElementById('symbolSearch').value.trim().toLowerCase();
  const repo = document.getElementById('symbolRepoFilter').value;
  const bucket = document.getElementById('symbolBucketFilter').value;
  const confidence = document.getElementById('symbolConfidenceFilter').value;
  document.querySelectorAll('[data-symbol]').forEach(detail => {
    const matchesQuery = !query || detail.dataset.symbol.toLowerCase().includes(query);
    const matchesRepo = !repo || (detail.dataset.repos || '').split(' ').includes(repo);
    const matchesBucket = !bucket || (detail.dataset.buckets || '').split(' ').includes(bucket);
    const matchesConfidence = !confidence || (detail.dataset.confidences || '').split(' ').includes(confidence);
    detail.style.display = matchesQuery && matchesRepo && matchesBucket && matchesConfidence ? '' : 'none';
  });
}

document.addEventListener('click', event => {
  const button = event.target.closest('[data-copy]');
  if (!button) return;
  navigator.clipboard?.writeText(button.dataset.copy || '');
  const oldText = button.textContent;
  button.textContent = 'copied';
  setTimeout(() => { button.textContent = oldText; }, 900);
});

document.getElementById('fileSearch').addEventListener('input', renderFileTree);
document.getElementById('fileRepoFilter').addEventListener('change', renderFileTree);
document.getElementById('graphSelect').addEventListener('change', renderGraph);
document.getElementById('symbolSearch').addEventListener('input', applySymbolFilters);
document.getElementById('symbolRepoFilter').addEventListener('change', applySymbolFilters);
document.getElementById('symbolBucketFilter').addEventListener('change', applySymbolFilters);
document.getElementById('symbolConfidenceFilter').addEventListener('change', applySymbolFilters);

renderFileTree();
renderGraph();
applySymbolFilters();
"""


if __name__ == "__main__":
    raise SystemExit(main())
