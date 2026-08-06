"""Single choke point for all tool filesystem access.

Single-file reads go through `resolve_safe_path`; multi-file scans (grep, function lookup) go through `iter_searchable_files`
Both enforce the same policy: root allowlist, `..` rejection, extension allowlist, size cap, denied subdirs, hidden paths, and symlink containment
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from app.settings import settings

# Stable literal roots the LLM can pass. Actual directories are resolved
# at call time from config + per-request Deps.
ROOT_MPMB_2014 = "./data/mpmb_source/"
ROOT_MPMB_2024 = "./data/mpmb_source_2024/"
ROOT_IMPORTS = "./data/imports_source/"
ROOT_UPLOADS_SESSION = "./data/uploads/session/"
ROOT_UPLOADS_GLOBAL = "./data/uploads/global/"
ROOT_UPLOADS_SHARED = "./data/uploads/shared/"

ALLOWED_ROOTS: frozenset[str] = frozenset(
    {ROOT_MPMB_2014, ROOT_MPMB_2024, ROOT_IMPORTS, ROOT_UPLOADS_SESSION, ROOT_UPLOADS_GLOBAL, ROOT_UPLOADS_SHARED}
)

# ? Upload roots resolve to per-user directories that may simply not exist yet; tools should report that as "nothing uploaded", not as a broken root
UPLOAD_ROOTS: frozenset[str] = frozenset({ROOT_UPLOADS_SESSION, ROOT_UPLOADS_GLOBAL, ROOT_UPLOADS_SHARED})

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".js", ".md", ".sample", ".yml", ".yaml", ".txt", ".json"})

DENIED_SUBDIRS: frozenset[str] = frozenset({".git", ".venv", "node_modules"})


@dataclass
class PathResolution:
    """Outcome of `resolve_safe_path`.

    On success, `resolved_path` is the real absolute path.
    On failure, `error` is an `[error] ...` string the tool returns to the LLM.
    """

    resolved_path: Optional[Path] = None
    error: Optional[str] = None


def _build_default_roots(deps) -> dict[str, Path]:
    """Resolve the literal root strings to real directories using Deps."""
    from app.config import config

    base = Path(config.upload_dir)
    return {
        ROOT_MPMB_2014: Path(config.mpmb_source_dir),
        ROOT_MPMB_2024: Path(config.mpmb_source_2024_dir),
        ROOT_IMPORTS: Path(config.imports_source_dir),
        ROOT_UPLOADS_SESSION: base / "session" / deps.session_id,
        ROOT_UPLOADS_GLOBAL: base / "global" / deps.user_id,
        ROOT_UPLOADS_SHARED: base / "shared",
    }


def _is_hidden_component(parts: tuple[str, ...]) -> bool:
    return any(p.startswith(".") and p not in (".", "..") for p in parts)


def missing_root_error(root: str) -> str:
    """Friendly error for a root whose directory does not exist"""
    if root == ROOT_UPLOADS_SESSION:
        return "[error] no files uploaded: this chat session has no uploaded files yet"
    if root == ROOT_UPLOADS_GLOBAL:
        return "[error] no files uploaded: your library is empty"
    if root == ROOT_UPLOADS_SHARED:
        return "[error] no files uploaded: the shared library is empty"
    return f"[error] root directory missing: {root}"


def iter_searchable_files(root_dir: Path, glob_pattern: str = "**/*") -> Iterator[tuple[Path, Path]]:
    """
    Yield `(absolute_path, relative_path)` for files passing the access policy

    Applies the same checks as `resolve_safe_path`: extension allowlist, denied subdirs, hidden paths, symlink containment,
    and the size cap (oversized files are skipped, not errors - scans should keep going)
    """
    try:
        root_real = root_dir.resolve(strict=False)
    except OSError:
        return

    for file_path in sorted(root_dir.glob(glob_pattern)):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        try:
            rel = file_path.resolve().relative_to(root_real)
        except (OSError, ValueError):
            continue
        if _is_hidden_component(rel.parts):
            continue
        if any(p in DENIED_SUBDIRS for p in rel.parts[:-1]):
            continue
        try:
            if file_path.stat().st_size > settings.tool_max_file_bytes:
                continue
        except OSError:
            continue
        yield file_path, Path(rel)


def resolve_safe_path(
    root: str,
    path: str,
    deps,
    roots: Optional[dict[str, Path]] = None,
) -> PathResolution:
    """Resolve `{root}/{path}` or return an `[error] ...` PathResolution."""
    if roots is None:
        roots = _build_default_roots(deps)

    if root not in ALLOWED_ROOTS:
        return PathResolution(error=f"[error] unknown root: {root}")
    if root not in roots:
        return PathResolution(error=f"[error] unknown root: {root}")

    if not path or path.strip() == "":
        return PathResolution(error="[error] empty path")

    p = Path(path)
    if p.is_absolute():
        return PathResolution(error="[error] absolute paths not allowed")
    if ".." in p.parts:
        return PathResolution(error="[error] parent-directory traversal not allowed")

    root_dir = roots[root]
    if not root_dir.exists():
        return PathResolution(error=missing_root_error(root))
    try:
        root_real = root_dir.resolve(strict=False)
    except OSError as e:
        return PathResolution(error=f"[error] root unavailable: {e}")

    candidate = root_dir / p
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as e:
        return PathResolution(error=f"[error] path resolution failed: {e}")

    try:
        rel = resolved.relative_to(root_real)
    except ValueError:
        return PathResolution(error="[error] path escapes root")

    if _is_hidden_component(rel.parts):
        return PathResolution(error="[error] hidden paths not allowed")
    for part in rel.parts:
        if part in DENIED_SUBDIRS:
            return PathResolution(error=f"[error] denied subdir: {part}")

    if not resolved.exists():
        return PathResolution(error=f"[error] path not found: {path}")
    if not resolved.is_file():
        return PathResolution(error=f"[error] not a file: {path}")

    if resolved.suffix.lower() not in ALLOWED_EXTENSIONS:
        return PathResolution(error=f"[error] extension not allowed: {resolved.suffix.lower()}")

    size = resolved.stat().st_size
    if size > settings.tool_max_file_bytes:
        mb = size / 1_048_576
        cap_mb = settings.tool_max_file_bytes / 1_048_576
        return PathResolution(
            error=f"[error] file too large: {mb:.1f} MB (cap {cap_mb:.1f} MB) — try mpmb_grep instead"
        )

    return PathResolution(resolved_path=resolved)
