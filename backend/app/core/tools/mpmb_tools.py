"""The three read-only MPMB source tools.

`Deps` carries per-request state (`session_id`, `edition`) that the
LLM cannot forge. Every tool takes `ctx: RunContext[Deps]` and
delegates path resolution to `source_paths.resolve_safe_path`.

All tools return `str`. Errors are `[error] <reason>` prefixes;
truncation is tagged inline with `[truncated: showing N of M ...]`.
"""

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic_ai import RunContext
from pydantic_ai.toolsets.function import FunctionToolset

from app.core.tools.source_paths import _build_default_roots, resolve_safe_path
from app.logger import get_logger
from app.settings import settings

logger = get_logger(__name__)

DEFAULT_READ_LINES = 500


@dataclass
class Deps:
    """Per-request context injected into tool calls."""

    session_id: str
    edition: str


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
    edition: Optional[str] = None,
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
        return f"[error] root directory missing: {root}"

    glob_pattern = path_glob or "**/*"
    from app.core.tools.source_paths import ALLOWED_EXTENSIONS, DENIED_SUBDIRS

    matches: list[str] = []
    max_matches = settings.tool_grep_max_matches
    total_matches = 0

    for file_path in sorted(root_dir.glob(glob_pattern)):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        try:
            rel = file_path.resolve().relative_to(root_dir.resolve())
        except ValueError:
            continue
        if any(p in DENIED_SUBDIRS or p.startswith(".") for p in rel.parts[:-1]):
            continue

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
        return f"[error] no matches for pattern: {pattern}"

    body = "\n".join(matches)
    if total_matches > max_matches:
        body += f"\n[truncated: showing {max_matches} of {total_matches} matches]"
    return body


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
    edition: Optional[str] = None,
) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return f"[error] invalid identifier: {name}"

    if root not in roots:
        return f"[error] unknown root: {root}"
    root_dir = roots[root]
    if not root_dir.exists():
        return f"[error] root directory missing: {root}"

    from app.core.tools.source_paths import ALLOWED_EXTENSIONS

    patterns = [re.compile(tmpl.format(name=re.escape(name))) for tmpl in _FUNCTION_PATTERN_TEMPLATES]

    for file_path in sorted(root_dir.glob("**/*.js")):
        if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            if any(p.search(line) for p in patterns):
                end_idx = _find_block_end(lines, idx)
                body = "\n".join(lines[idx : end_idx + 1])
                try:
                    rel = file_path.resolve().relative_to(root_dir.resolve())
                except ValueError:
                    rel = Path(file_path.name)
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
    def mpmb_read(
        ctx: RunContext[Deps],
        root: str,
        path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> str:
        """Read a file from the MPMB source. Returns text or an `[error] ...` string."""
        roots = _build_default_roots(ctx.deps)
        logger.info(f"tool.mpmb_read root={root} path={path} range={start_line}-{end_line}")
        return _mpmb_read_impl(roots, ctx.deps, root, path, start_line, end_line)

    @toolset.tool
    def mpmb_grep(
        ctx: RunContext[Deps],
        root: str,
        pattern: str,
        path_glob: Optional[str] = None,
        edition: Optional[str] = None,
    ) -> str:
        """Search files under `root` for `pattern`. Returns matches or `[error] ...`."""
        roots = _build_default_roots(ctx.deps)
        logger.info(f"tool.mpmb_grep root={root} pattern={pattern!r} glob={path_glob}")
        return _mpmb_grep_impl(roots, ctx.deps, root, pattern, path_glob, edition)

    @toolset.tool
    def mpmb_function(
        ctx: RunContext[Deps],
        root: str,
        name: str,
        edition: Optional[str] = None,
    ) -> str:
        """Fetch the full body of a function or variable by name. Returns source or `[error] ...`."""
        roots = _build_default_roots(ctx.deps)
        logger.info(f"tool.mpmb_function root={root} name={name}")
        return _mpmb_function_impl(roots, ctx.deps, root, name, edition)

    return toolset
