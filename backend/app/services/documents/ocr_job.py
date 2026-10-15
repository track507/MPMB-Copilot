"""
The "ocr" job: transcribe the empty pages of an uploaded PDF off the request path

Attempts persist in a progress file beside the cache pair and survive a restart
"""

import hashlib
import json
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any, Optional

from app.config import config
from app.logger import get_logger
from app.services.documents import cache, registry, service
from app.services.documents.errors import DocumentError
from app.services.documents.protocol import CachedDocument, CacheScope, DocumentReader, OcrState, normalize
from app.services.jobs.protocol import Job

logger = get_logger(__name__)

KIND = "ocr"
MAX_ATTEMPTS = 3
EXTRACTOR_ID = "pdf"
_PROGRESS = "progress"


@dataclass
class OcrProgress:
    attempts: int = 0
    stalled: bool = False
    unavailable: str = ""
    error: str = ""


def _progress_path(scope: CacheScope, digest: str, base: Optional[Path] = None) -> Path:
    _, json_path = cache.sidecar_paths(scope, digest, EXTRACTOR_ID, _PROGRESS, base)
    return json_path


def read_progress(scope: CacheScope, digest: str, base: Optional[Path] = None) -> OcrProgress:
    """The persisted progress, or a fresh one when the file is missing or unreadable"""
    try:
        raw = json.loads(_progress_path(scope, digest, base).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return OcrProgress()
    if not isinstance(raw, dict):
        return OcrProgress()
    known = {f.name for f in fields(OcrProgress)}
    try:
        return OcrProgress(**{k: v for k, v in raw.items() if k in known})
    except TypeError:
        return OcrProgress()


def write_progress(scope: CacheScope, digest: str, progress: OcrProgress, base: Optional[Path] = None) -> None:
    path = _progress_path(scope, digest, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    cache.atomic_write(path, json.dumps(asdict(progress)))


def clear_progress(scope: CacheScope, digest: str, base: Optional[Path] = None) -> None:
    _progress_path(scope, digest, base).unlink(missing_ok=True)


def should_run(progress: OcrProgress) -> bool:
    return not progress.stalled and progress.attempts < MAX_ATTEMPTS


def upload_cache_scope(scope: str, owner_user_id: str, tenant_id: str) -> CacheScope:
    """The cache bucket an upload's derived text lives in"""
    return CacheScope.shared(tenant_id) if scope == "shared" else CacheScope.for_user(owner_user_id)


def job_for(tenant_id: str, storage_key: str, cache_scope: CacheScope, digest: str, extension: str) -> Optional[Job]:
    """The OCR job for an uploaded file, or None when it is not a PDF, not an upload, or OCR is off"""
    ext = extension.lower()
    if ext != ".pdf" or cache_scope.kind == "source_root":
        return None
    versions = registry.candidate_versions(ext)
    if len(versions) < 2:
        return None
    payload: dict[str, Any] = {
        "storage_key": storage_key,
        "scope_kind": cache_scope.kind,
        "scope_key": cache_scope.key,
        "file_hash": digest,
        "extension": ext,
    }
    key = f"{KIND}:{tenant_id}:{cache_scope.kind}:{cache_scope.key}:{digest}:{versions[0]}"
    return Job(kind=KIND, tenant_id=tenant_id, payload=payload, key=key)


def _scope_from(kind: str, key: str) -> CacheScope:
    if kind == "shared":
        return CacheScope.shared(key)
    if kind == "user":
        return CacheScope.for_user(key)
    raise ValueError(f"no OCR for cache scope kind {kind!r}")


def _resolve_upload(storage_key: str, *, tenant_id: str) -> Optional[Path]:
    """
    The upload's file, or None when the key escapes the tenants tree, names another tenant, or the file is gone
    """
    tenants = Path(config.tenants_dir).resolve()
    path = (Path(config.data_dir) / storage_key).resolve()
    if not path.is_relative_to(tenants):
        return None
    identity = _upload_identity(path)
    # ! The job's tenant is the authority: a key naming another tenant is a forged or misrouted queue row
    if identity is None or identity[0] != tenant_id:
        logger.warning("ocr_job_foreign_tenant", tenant_id=tenant_id)
        return None
    return path if path.is_file() else None


def _snapshot(path: Path, digest: str, into: Path) -> Optional[Path]:
    """
    A private copy of the upload, made only when its bytes still hash to digest

    ! Every later read parses this copy, so the bytes checked are the bytes parsed
    """
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        return None
    copy = into / f"upload{path.suffix}"
    copy.write_bytes(data)
    return copy


def run(job: Job) -> None:
    """Transcribe the empty pages of one upload and cache the result under the with-transcriber version"""
    payload = job.payload
    digest = str(payload["file_hash"])
    extension = str(payload["extension"])
    scope = _scope_from(str(payload["scope_kind"]), str(payload["scope_key"]))

    path = _resolve_upload(str(payload["storage_key"]), tenant_id=job.tenant_id)
    with tempfile.TemporaryDirectory(prefix="ocr-") as scratch:
        snapshot = None if path is None else _snapshot(path, digest, Path(scratch))
        if snapshot is None:
            logger.info("ocr_job_stale", tenant_id=job.tenant_id, file_hash=digest)
            return
        _transcribe(snapshot, scope, digest, extension)


def _transcribe(path: Path, scope: CacheScope, digest: str, extension: str) -> None:
    """The job's work on a verified private copy; path is never the live upload"""
    progress = read_progress(scope, digest)
    if not should_run(progress):
        return

    extractor = registry.ocr_extractor_for(extension)
    if extractor is None:
        transcriber = registry.configured_transcriber()
        reason = "OCR is off" if transcriber is None else (transcriber.check_availability() or "OCR is unavailable")
        write_progress(scope, digest, replace(progress, unavailable=reason))
        return

    if cache.read_pair(scope, digest, EXTRACTOR_ID, extractor.version) is not None:
        clear_progress(scope, digest)
        return
    if not service.ensure_extracted(path, scope).pages_without_text:
        clear_progress(scope, digest)
        return

    progress = replace(progress, attempts=progress.attempts + 1, unavailable="")
    write_progress(scope, digest, progress)
    try:
        extraction = extractor.extract(path)
        if normalize(extraction.text) != extraction.text:
            raise DocumentError("extraction_failed", "the OCR extractor returned text that is not normalized")
        cache.write_pair(scope, digest, EXTRACTOR_ID, extractor.version, extraction, extension)
    except Exception as e:
        write_progress(scope, digest, replace(progress, stalled=progress.attempts >= MAX_ATTEMPTS, error=str(e)[:500]))
        raise
    clear_progress(scope, digest)


def status(path: Path, scope: CacheScope) -> OcrState:
    """Where OCR stands for one file's empty pages; never loads the engine"""
    versions = registry.candidate_versions(path.suffix)
    if len(versions) < 2:
        return "off"
    digest = service.file_hash(path)
    if cache.read_pair(scope, digest, EXTRACTOR_ID, versions[0]) is not None:
        return "done"
    progress = read_progress(scope, digest)
    if progress.stalled:
        return "stalled"
    if progress.unavailable:
        return "unavailable"
    return "pending"


def _upload_identity(path: Path) -> Optional[tuple[str, str]]:
    """(tenant_id, storage_key) for a file under the tenants tree, else None"""
    try:
        relative = path.resolve().relative_to(Path(config.data_dir).resolve())
    except ValueError:
        return None
    if len(relative.parts) < 3 or relative.parts[0] != "tenants":
        return None
    return relative.parts[1], relative.as_posix()


class OcrAwareReader:
    """
    A DocumentReader that queues OCR for an upload whose text layer left pages empty

    The returned summary carries the OCR state under "ocr"; a read never waits on OCR
    """

    def __init__(self, reader: DocumentReader, submit: Callable[[Job], None]) -> None:
        self._reader = reader
        self._submit = submit

    def lookup(self, path: Path, scope: CacheScope) -> Optional[CachedDocument]:
        return self._reader.lookup(path, scope)

    def ensure_extracted(self, path: Path, scope: CacheScope) -> CachedDocument:
        document = self._reader.ensure_extracted(path, scope)
        if not document.pages_without_text or scope.kind == "source_root":
            return document
        state = status(path, scope)
        if state in ("pending", "unavailable"):
            identity = _upload_identity(path)
            if identity is not None:
                job = job_for(identity[0], identity[1], scope, service.file_hash(path), path.suffix)
                if job is not None:
                    self._submit(job)
        return replace(document, summary={**document.summary, "ocr": state})
