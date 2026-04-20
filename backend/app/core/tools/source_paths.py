"""Single choke point for all tool filesystem access.

Every tool goes through `resolve_safe_path` before touching disk. The
function enforces root allowlist, `..` rejection, extension allowlist,
size cap, denied subdirs, and symlink containment.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.settings import settings

# Stable literal roots the LLM can pass. Actual directories are resolved
# at call time from config + per-request Deps.
ROOT_MPMB_2014 = "./data/mpmb_source/"
ROOT_MPMB_2024 = "./data/mpmb_source_2024/"
ROOT_UPLOADS_SESSION = "./data/uploads/session/"
ROOT_UPLOADS_GLOBAL = "./data/uploads/global/"

ALLOWED_ROOTS: frozenset[str] = frozenset({ROOT_MPMB_2014, ROOT_MPMB_2024, ROOT_UPLOADS_SESSION, ROOT_UPLOADS_GLOBAL})

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".js", ".md", ".sample", ".yml", ".yaml", ".txt"})

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
    """Resolve the four literal root strings to real directories using Deps."""
    from app.config import config

    session_dir = Path(config.upload_dir) / deps.session_id
    global_dir = Path(config.upload_dir) / "global"
    return {
        ROOT_MPMB_2014: Path(config.mpmb_source_dir),
        ROOT_MPMB_2024: Path(config.mpmb_source_2024_dir),
        ROOT_UPLOADS_SESSION: session_dir,
        ROOT_UPLOADS_GLOBAL: global_dir,
    }


def _is_hidden_component(parts: tuple[str, ...]) -> bool:
    return any(p.startswith(".") and p not in (".", "..") for p in parts)


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
