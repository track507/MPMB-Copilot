"""Single choke point for all tool filesystem access.

Single-file reads go through `resolve_safe_path`; multi-file scans (grep, function lookup) go through `iter_searchable_files`
Both enforce the same policy: root allowlist, `..` rejection, extension allowlist, size cap, denied subdirs, hidden paths, and symlink containment
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

from app.services import documents
from app.services.documents import CachedDocument, CacheScope, DocumentError
from app.settings import settings

# Stable literal roots the LLM can pass. Actual directories are resolved at call time from config + per-request Deps
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

# ! Documents are readable only because an adapter extracts them; the set widens with documents.EXTRACTABLE_EXTENSIONS
ALLOWED_EXTENSIONS: frozenset[str] = (
    frozenset({".js", ".md", ".sample", ".yml", ".yaml", ".txt", ".json"}) | documents.EXTRACTABLE_EXTENSIONS
)

# * Which cache bucket each root's extractions land in; upload roots resolve per request from the caller's identity
_SOURCE_ROOT_CACHE_KEYS: dict[str, str] = {
    ROOT_MPMB_2014: "mpmb_source",
    ROOT_MPMB_2024: "mpmb_source_2024",
    ROOT_IMPORTS: "imports_source",
}

DENIED_SUBDIRS: frozenset[str] = frozenset({".git", ".venv", "node_modules"})


@dataclass
class PathResolution:
    """Outcome of `resolve_safe_path`.

    On success, `resolved_path` is the real absolute path.
    On failure, `error` is an `[error] ...` string the tool returns to the LLM.
    """

    resolved_path: Optional[Path] = None
    error: Optional[str] = None
    document: Optional[CachedDocument] = None


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


def cache_scope_for(root: str, deps: Any) -> CacheScope:
    """
    The extraction cache bucket for a root, derived from the root that matched and never from a tool argument

    Only this and user_id are request-derived, which is why extraction takes a CacheScope rather than the whole deps
    """
    if root == ROOT_UPLOADS_SHARED:
        return CacheScope.shared()
    if root in (ROOT_UPLOADS_SESSION, ROOT_UPLOADS_GLOBAL):
        return CacheScope.for_user(deps.user_id)
    return CacheScope.for_source_root(_SOURCE_ROOT_CACHE_KEYS[root])


def resolve_readable(path: Path, cache_scope: CacheScope, *, enforce_size_cap: bool = True) -> PathResolution:
    """
    The path a tool should actually read: the file itself for text formats, its extracted sidecar for documents

    Called only after resolve_safe_path's checks pass, because the root allowlist is what makes cache_scope valid
    """
    if not documents.is_extractable(path.suffix):
        return PathResolution(resolved_path=path)

    try:
        document = documents.ensure_extracted(path, cache_scope)
    except DocumentError as e:
        return PathResolution(error=e.as_tool_error())

    pages = document.summary.get("pages")
    if pages and len(document.pages_without_text) >= pages:
        # ? A partly scanned guide still reads; only a document with no text anywhere is refused outright
        return PathResolution(
            error=DocumentError(
                "no_text_layer", f"{path.name} has no text layer on any page; OCR is not available yet"
            ).as_tool_error()
        )

    if enforce_size_cap:
        size = document.text_path.stat().st_size
        cap = int(settings.document_setting("max_extracted_bytes"))
        if size > cap:
            return PathResolution(
                error=DocumentError(
                    "extracted_too_large",
                    f"{path.name} extracts to {size / 1_048_576:.1f} MB of text (cap {cap / 1_048_576:.1f} MB)"
                    " - use mpmb_outline to find a section, then mpmb_grep or a line-range mpmb_read",
                ).as_tool_error()
            )

    return PathResolution(resolved_path=document.text_path, document=document)


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
        # * A document's raw bytes are not what gets read, so its size is judged by the caller's extraction budget instead
        if not documents.is_extractable(file_path.suffix):
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
    *,
    enforce_size_cap: bool = True,
) -> PathResolution:
    """
    Resolve `{root}/{path}` to the path a tool should read, or return an `[error] ...` PathResolution

    For a document that path is its extracted sidecar, with the outline and summary on `document`
    `enforce_size_cap=False` is for callers that read metadata rather than the whole text, like mpmb_outline
    """
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

    # ! Documents skip the raw byte cap: a 300-page PDF exceeds it while its extracted text is what the model reads
    if documents.is_extractable(resolved.suffix):
        return resolve_readable(resolved, cache_scope_for(root, deps), enforce_size_cap=enforce_size_cap)

    size = resolved.stat().st_size
    if enforce_size_cap and size > settings.tool_max_file_bytes:
        mb = size / 1_048_576
        cap_mb = settings.tool_max_file_bytes / 1_048_576
        return PathResolution(
            error=f"[error] file too large: {mb:.1f} MB (cap {cap_mb:.1f} MB) - try mpmb_grep instead"
        )

    return PathResolution(resolved_path=resolved)
