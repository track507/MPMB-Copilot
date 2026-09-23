"""
The one entry point the tool layer calls to turn a document into readable text

Hashes the file, consults the owner-keyed cache, and extracts on a miss
Never reaches the database, so the domain can call it without inheriting a persistence dependency
"""

import hashlib
import threading
from pathlib import Path
from typing import Any, Optional

from app.services.documents import cache, registry
from app.services.documents.cache import CachedDocument
from app.services.documents.errors import DocumentError
from app.services.documents.protocol import CacheScope, normalize

_CHUNK_BYTES = 1024 * 1024
_HASH_MEMO_LIMIT = 1024

# ? Keyed on path, size and mtime so a read does not re-hash a 50 MB guide, while an edited file still re-hashes
_hash_memo: dict[tuple[str, int, int], str] = {}
_hash_lock = threading.Lock()


def file_hash(path: Path) -> str:
    """SHA-256 of the file's bytes, the key the cache and the upload registry share"""
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    with _hash_lock:
        known = _hash_memo.get(key)
    if known is not None:
        return known

    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(_CHUNK_BYTES):
            digest.update(chunk)
    value = digest.hexdigest()

    with _hash_lock:
        if len(_hash_memo) >= _HASH_MEMO_LIMIT:
            _hash_memo.clear()
        _hash_memo[key] = value
    return value


def lookup(path: Path, scope: CacheScope) -> Optional[CachedDocument]:
    """
    The cached extraction for a file, or None, without ever extracting

    Grep and the upload manifest use this, because both must stay cheap and never trigger work on their own
    """
    extractor = registry.extractor_for(path.suffix)
    extractor_id = registry.extractor_id(path.suffix)
    if extractor is None or extractor_id is None:
        return None
    return cache.read_pair(scope, file_hash(path), extractor_id, extractor.version)


def cached_summary(file_hash: str, extension: str, scope: CacheScope) -> Optional[dict[str, Any]]:
    """
    A cached extraction's summary looked up by content hash, without reading the file or extracting

    For callers that already hold the hash, like the per-turn upload manifest, which must never trigger extraction
    """
    extractor = registry.extractor_for(extension)
    extractor_id = registry.extractor_id(extension)
    if extractor is None or extractor_id is None:
        return None
    try:
        document = cache.read_pair(scope, file_hash, extractor_id, extractor.version)
    except ValueError:
        return None
    return document.summary if document is not None else None


def release(file_hash: str, extension: str, scope: CacheScope) -> int:
    """
    Delete every extracted sidecar for these bytes in one bucket

    Call only once nothing in the bucket references the hash; deciding that is the upload registry's job, not this module's
    """
    if not registry.is_extractable(extension):
        return 0
    return cache.unlink_hash(scope, file_hash)


def ensure_extracted(path: Path, scope: CacheScope) -> CachedDocument:
    """
    The cached extraction for a file, extracting and caching it on a miss

    Raises DocumentError, which the tool layer renders as an [error] string
    """
    extractor = registry.extractor_for(path.suffix)
    extractor_id = registry.extractor_id(path.suffix)
    if extractor is None or extractor_id is None:
        readable = ", ".join(sorted(registry.EXTRACTABLE_EXTENSIONS))
        raise DocumentError(
            "unsupported_format", f"no reader for {path.suffix.lower()} files; readable documents are {readable}"
        )

    reason = registry.availability(path.suffix)
    if reason is not None:
        raise DocumentError("extractor_unavailable", reason)

    digest = file_hash(path)
    cached = cache.read_pair(scope, digest, extractor_id, extractor.version)
    if cached is not None:
        return cached

    extraction = extractor.extract(path)
    # ! Line numbers are computed on the adapter's text, so text that normalize() would still change has wrong ones
    # ? Checked here rather than trusted, so a future OCR or Docling adapter cannot skip the contract silently
    if normalize(extraction.text) != extraction.text:
        raise DocumentError(
            "extraction_failed", f"the {extractor_id} extractor returned text that is not normalized; this is a bug"
        )
    return cache.write_pair(scope, digest, extractor_id, extractor.version, extraction, path.suffix)
