"""The four read-only MPMB source tools.

`mpmb_search` queries the indexed corpus via the retriever; the other
three (`mpmb_read`, `mpmb_grep`, `mpmb_function`) read the cloned
source trees through the `source_paths` access policy.

`Deps` carries per-request state (`session_id`, `edition`) that the
LLM cannot forge. Every tool takes `ctx: RunContext[Deps]`.

All tools return `str`. Errors are `[error] <reason>` prefixes;
truncation is tagged inline with `[truncated: showing N of M ...]`.
"""

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from pydantic_ai import RunContext
from pydantic_ai.toolsets.function import FunctionToolset

from app.core.tools.source_paths import (
    _build_default_roots,
    iter_searchable_files,
    missing_root_error,
    resolve_safe_path,
)
from app.logger import get_logger
from app.settings import settings

logger = get_logger(__name__)

DEFAULT_READ_LINES = 500

# ! Must stay in sync with source_paths.ALLOWED_ROOTS (asserted in tests)
# ? Literal puts the valid roots in the tool JSON schema itself, where the model is least likely to invent paths
SourceRoot = Literal[
    "./data/mpmb_source/",
    "./data/mpmb_source_2024/",
    "./data/imports_source/",
    "./data/uploads/session/",
    "./data/uploads/global/",
]


@dataclass
class Deps:
    """Per-request context injected into tool calls."""

    session_id: str
    edition: str
    # ! Chunk keys (file:start-end) returned by mpmb_search this turn, used to detect when repeated searches keep surfacing the same context
    seen_chunks: set[str] = field(default_factory=set)
    # ! Per-turn retrieval trace: one citation entry per mpmb_search call (no chunk bodies); rag_engine reads this after the run
    trace: list[dict] = field(default_factory=list)


# * Implementations (testable without PydanticAI)
def _mpmb_read_impl(
    roots: dict[str, Path],
    deps: Deps,
    root: str,
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> str:
    resolution = resolve_safe_path(root, path, deps, roots=roots)
    if resolution.error:
        return resolution.error
    resolved = resolution.resolved_path

    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"[error] read failed: {e}"

    lines = text.splitlines()
    total = len(lines)

    if start_line is None and end_line is None:
        max_lines = settings.tool_read_max_lines
        if total > max_lines:
            shown = lines[:max_lines]
            return "\n".join(shown) + f"\n[truncated: showing {max_lines} of {total} lines]"
        return text

    s = max(1, start_line or 1)
    e = min(total, end_line or total)
    if s > total:
        return f"[error] start_line {s} exceeds file length ({total})"
    slice_lines = lines[s - 1 : e]

    max_lines = settings.tool_read_max_lines
    if len(slice_lines) > max_lines:
        slice_lines = slice_lines[:max_lines]
        return "\n".join(slice_lines) + f"\n[truncated: showing {max_lines} of {e - s + 1} lines]"
    return "\n".join(slice_lines)


def _mpmb_grep_impl(
    roots: dict[str, Path],
    deps: Deps,
    root: str,
    pattern: str,
    path_glob: Optional[str] = None,
) -> str:
    if len(pattern) > settings.tool_grep_pattern_max_len:
        return f"[error] pattern too long: {len(pattern)} chars (max {settings.tool_grep_pattern_max_len})"

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"[error] invalid regex: {e}"

    if root not in roots:
        return f"[error] unknown root: {root}"
    root_dir = roots[root]
    if not root_dir.exists():
        return missing_root_error(root)

    matches: list[str] = []
    max_matches = settings.tool_grep_max_matches
    total_matches = 0

    for file_path, rel in iter_searchable_files(root_dir, path_glob or "**/*"):
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        t0 = time.perf_counter()
        for lineno, line in enumerate(text.splitlines(), start=1):
            if (time.perf_counter() - t0) > settings.tool_grep_file_timeout_sec:
                break
            if regex.search(line):
                total_matches += 1
                if len(matches) < max_matches:
                    matches.append(f"{rel.as_posix()}:{lineno}: {line.rstrip()}")

    if not matches:
        # ? Zero matches is a valid answer, not a failure - an [error] prefix would tell the model not to trust the result and paint an error pill
        return (
            f'No matches for pattern "{pattern}" under {root}. '
            "The pattern does not occur in this source tree; try a broader pattern or a different root."
        )

    body = "\n".join(matches)
    if total_matches > max_matches:
        body += f"\n[truncated: showing {max_matches} of {total_matches} matches]"
    return body


async def _mpmb_search_impl(deps: Deps, query: str, edition: Optional[str] = None) -> str:
    # ? Lazy import keeps the tool module importable without the retrieval stack
    from app.core.retriever import retriever

    try:
        result = await retriever.retrieve(query=query, edition=edition)
    except Exception as e:
        deps.trace.append({"tool": "mpmb_search", "query": query, "edition": edition, "chunks": []})
        return f"[error] retrieval unavailable: {e}. Fall back to mpmb_grep or mpmb_function for symbol-level lookup."

    if result.is_empty:
        deps.trace.append(
            {
                "tool": "mpmb_search",
                "query": query,
                "edition": (result.query_analysis.edition if result.query_analysis else None) or edition,
                "chunks": [],
            }
        )
        return (
            f'No indexed chunks matched "{query}"'
            + (f" (edition={edition})" if edition else "")
            + ". Rephrase the query, or use mpmb_grep for exact symbols."
        )

    def _chunk_key(chunk: dict) -> str:
        return f"{chunk.get('source_file', '?')}:{chunk.get('start_line')}-{chunk.get('end_line')}"

    all_chunks = [*result.authoritative, *result.examples]
    keys = {_chunk_key(c) for c in all_chunks}
    # ? Nudge the model to stop searching once results mostly repeat earlier ones
    overlap = len(keys & deps.seen_chunks) / len(keys) if keys else 0.0
    repeated = bool(deps.seen_chunks) and overlap >= 0.7
    deps.seen_chunks |= keys
    deps.trace.append(
        {
            "tool": "mpmb_search",
            "query": query,
            "edition": (result.query_analysis.edition if result.query_analysis else None) or edition,
            "chunks": [
                {
                    "source_file": c.get("source_file"),
                    "start_line": c.get("start_line"),
                    "end_line": c.get("end_line"),
                    "tier": c.get("source_tier"),
                    "score": round(float(c.get("score", 0.0)), 4),
                    "edition": c.get("edition"),
                    "chunk_type": c.get("chunk_type"),
                    "object_type": (c.get("metadata") or {}).get("object_type"),
                }
                for c in all_chunks
            ],
        }
    )

    sections: list[str] = []
    if repeated:
        sections.append(
            "[note] These results largely repeat earlier searches this turn. "
            "You likely have enough context - answer now, or use mpmb_read/mpmb_function "
            "for an exact symbol instead of searching again."
        )
    section_specs = (
        ("AUTHORITATIVE (trust these for correctness)", result.authoritative),
        ("EXAMPLES (implementation patterns)", result.examples),
    )
    for title, chunks in section_specs:
        if not chunks:
            continue
        sections.append(f"## {title}")
        for i, chunk in enumerate(chunks, start=1):
            loc = str(chunk.get("source_file", "?"))
            start = chunk.get("start_line")
            end = chunk.get("end_line")
            if start and end:
                loc = f"{loc}:{start}-{end}"
            sections.append(
                f"[{i}] {loc} (edition={chunk.get('edition', '?')}, "
                f"tier={chunk.get('source_tier', '?')}, score={float(chunk.get('score', 0.0)):.2f})\n"
                f"{chunk.get('content', '')}"
            )

    intent_name = result.intent.primary.value if result.intent else "unknown"
    resolved_edition = (result.query_analysis.edition if result.query_analysis else None) or edition or "both"
    sections.append(f"[retrieval: intent={intent_name}, edition={resolved_edition}, chunks={result.total_chunks}]")
    return "\n\n".join(sections)


_FUNCTION_PATTERN_TEMPLATES = (
    r"^\s*var\s+{name}\s*=",
    r"^\s*function\s+{name}\s*\(",
    r"^\s*{name}\s*=\s*function",
)


def _mpmb_function_impl(
    roots: dict[str, Path],
    deps: Deps,
    root: str,
    name: str,
) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return f"[error] invalid identifier: {name}"

    if root not in roots:
        return f"[error] unknown root: {root}"
    root_dir = roots[root]
    if not root_dir.exists():
        return missing_root_error(root)

    patterns = [re.compile(tmpl.format(name=re.escape(name))) for tmpl in _FUNCTION_PATTERN_TEMPLATES]

    for file_path, rel in iter_searchable_files(root_dir, "**/*.js"):
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            if any(p.search(line) for p in patterns):
                end_idx = _find_block_end(lines, idx)
                body = "\n".join(lines[idx : end_idx + 1])
                return f"// {rel.as_posix()}:{idx + 1}\n{body}"

    return f"[error] function/variable not found: {name}"


def _find_block_end(lines: list[str], start: int) -> int:
    """Follow brace depth from `start` until balanced; bail at +500 lines."""
    depth = 0
    seen_open = False
    limit = min(len(lines), start + 500)
    for i in range(start, limit):
        line = lines[i]
        for ch in line:
            if ch == "{":
                depth += 1
                seen_open = True
            elif ch == "}":
                depth -= 1
                if seen_open and depth <= 0:
                    if line.rstrip().endswith(";") or i + 1 >= len(lines):
                        return i
                    if i + 1 < len(lines) and lines[i + 1].strip().startswith(";"):
                        return i + 1
                    return i
        if seen_open is False and line.rstrip().endswith(";"):
            return i
    return limit - 1


# * PydanticAI toolset factory
def build_mpmb_toolset() -> FunctionToolset[Deps]:
    """Return a `FunctionToolset` bound to `Deps` with the three tools."""
    toolset: FunctionToolset[Deps] = FunctionToolset()

    @toolset.tool
    async def mpmb_search(
        ctx: RunContext[Deps],
        query: str,
        edition: Optional[Literal["2014", "2024"]] = None,
    ) -> str:
        """
        Search the indexed MPMB sources for code chunks relevant to a query

        Use for any MPMB question about identifiers, registries (SpellsList, ClassList, FeatsList, ...), object types (race, subclass, spell, feat, item, background, source),
        or how to write or fix MPMB content
        Phrase the query in English
        Returns ranked chunks grouped into AUTHORITATIVE rules and EXAMPLES, cited as file:start-end
        Omit `edition` to let retrieval infer it from the query. Follow up with mpmb_read or mpmb_function when you need exact verbatim code
        """
        logger.info(f"tool.mpmb_search query={query!r} edition={edition}")
        return await _mpmb_search_impl(ctx.deps, query, edition)

    @toolset.tool
    def mpmb_read(
        ctx: RunContext[Deps],
        root: SourceRoot,
        path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> str:
        """
        Read a file (or a line range) verbatim from an MPMB source root

        Use when you need exact code from a known path, typically after mpmb_grep or mpmb_function located the file `path` is relative to `root`
        Returns the text, ending with `[truncated: ...]` when capped; `[error] ...` means the call failed - try a different path or tool
        """
        roots = _build_default_roots(ctx.deps)
        logger.info(f"tool.mpmb_read root={root} path={path} range={start_line}-{end_line}")
        return _mpmb_read_impl(roots, ctx.deps, root, path, start_line, end_line)

    @toolset.tool
    def mpmb_grep(
        ctx: RunContext[Deps],
        root: SourceRoot,
        pattern: str,
        path_glob: Optional[str] = None,
    ) -> str:
        """
        Regex-search every file under a root, returning `file:line: text` matches

        Use to find symbols, attributes, or conventions across files
        `path_glob` narrows the file set (e.g. `**/*.js`)
        A "No matches" response is a valid result meaning the pattern is absent - do not retry the identical call
        """
        roots = _build_default_roots(ctx.deps)
        logger.info(f"tool.mpmb_grep root={root} pattern={pattern!r} glob={path_glob}")
        return _mpmb_grep_impl(roots, ctx.deps, root, pattern, path_glob)

    @toolset.tool
    def mpmb_function(
        ctx: RunContext[Deps],
        root: SourceRoot,
        name: str,
    ) -> str:
        """
        Fetch the complete body of a named function or `var` declaration

        Use when the user names a specific engine function or registry variable and you need its exact definition
        Returns the source prefixed with a `// file:line` comment, or `[error] ... not found` if the identifier is not declared under this root
        """
        roots = _build_default_roots(ctx.deps)
        logger.info(f"tool.mpmb_function root={root} name={name}")
        return _mpmb_function_impl(roots, ctx.deps, root, name)

    return toolset
