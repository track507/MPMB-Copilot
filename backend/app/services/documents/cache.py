"""
Owner-keyed sidecar cache for extracted documents

Filesystem only by design: the upload registry owns reference counting, so this module never reaches the database
Layout under config.extracted_dir: <user_id>/, shared/, and _source_roots/<root>/, each holding <hash>.<id>.<version>.{txt,json}
"""

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from app.config import config
from app.logger import get_logger
from app.services.documents.protocol import CacheScope, Extraction, OutlineEntry

logger = get_logger(__name__)

# ! The stem is our own digest, checked before use, so no filename component is ever user-controlled
_HASH = re.compile(r"[0-9a-f]{64}")
_SAFE_PART = re.compile(r"[A-Za-z0-9_-]+")

SHARED_DIR = "shared"
SOURCE_ROOTS_DIR = "_source_roots"


@dataclass(frozen=True)
class CachedDocument:
    """A completed extraction on disk: the text the tools read and the metadata the outline serves"""

    text_path: Path
    outline: list[OutlineEntry]
    pages_without_text: list[int]
    summary: dict[str, Any]


def base_dir() -> Path:
    return Path(config.extracted_dir)


def bucket_dir(scope: CacheScope, base: Optional[Path] = None) -> Path:
    root = base if base is not None else base_dir()
    if scope.kind == "shared":
        return root / SHARED_DIR
    if scope.kind == "source_root":
        return root / SOURCE_ROOTS_DIR / scope.key
    return root / scope.key


def _stem(file_hash: str, extractor_id: str, version: str) -> str:
    if not _HASH.fullmatch(file_hash):
        raise ValueError(f"not a sha256 hex digest: {file_hash!r}")
    if not _SAFE_PART.fullmatch(extractor_id) or not _SAFE_PART.fullmatch(version):
        raise ValueError(f"unsafe extractor id or version: {extractor_id!r} {version!r}")
    return f"{file_hash}.{extractor_id}.{version}"


def sidecar_paths(
    scope: CacheScope, file_hash: str, extractor_id: str, version: str, base: Optional[Path] = None
) -> tuple[Path, Path]:
    stem = _stem(file_hash, extractor_id, version)
    bucket = bucket_dir(scope, base)
    return bucket / f"{stem}.txt", bucket / f"{stem}.json"


def read_pair(
    scope: CacheScope, file_hash: str, extractor_id: str, version: str, base: Optional[Path] = None
) -> Optional[CachedDocument]:
    """
    The cached extraction, or None on any miss

    The json is written last and is the completion marker, so a txt without a parseable json is a miss, never a partial hit
    """
    text_path, json_path = sidecar_paths(scope, file_hash, extractor_id, version, base)
    if not text_path.is_file():
        return None
    try:
        meta = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict):
        return None
    try:
        outline = [OutlineEntry(**entry) for entry in meta.get("outline", [])]
    except TypeError:
        return None
    return CachedDocument(
        text_path=text_path,
        outline=outline,
        pages_without_text=[int(p) for p in meta.get("pages_without_text", [])],
        summary=dict(meta.get("summary", {})),
    )


def write_pair(
    scope: CacheScope,
    file_hash: str,
    extractor_id: str,
    version: str,
    extraction: Extraction,
    original_extension: str,
    base: Optional[Path] = None,
) -> CachedDocument:
    """
    Persist an extraction as a txt and json pair and return it as a cache hit would

    Each file lands through a temp file and os.replace, and the json goes second, so readers never see a torn pair
    """
    text_path, json_path = sidecar_paths(scope, file_hash, extractor_id, version, base)
    text_path.parent.mkdir(parents=True, exist_ok=True)

    meta = {
        "outline": [entry.__dict__ for entry in extraction.outline],
        "pages_without_text": extraction.pages_without_text,
        "summary": extraction.summary,
        "extractor": extractor_id,
        "version": version,
        "original_extension": original_extension.lower(),
    }
    _atomic_write(text_path, extraction.text)
    _atomic_write(json_path, json.dumps(meta, ensure_ascii=True))

    return CachedDocument(
        text_path=text_path,
        outline=list(extraction.outline),
        pages_without_text=list(extraction.pages_without_text),
        summary=dict(extraction.summary),
    )


def _atomic_write(path: Path, content: str) -> None:
    temp = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    try:
        # ? newline="" keeps \n as written, so Windows cannot turn the stream into \r\n and shift every line count
        with temp.open("w", encoding="utf-8", newline="") as out:
            out.write(content)
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def unlink_hash(scope: CacheScope, file_hash: str, base: Optional[Path] = None) -> int:
    """
    Remove every sidecar for a hash in one bucket, across all extractor versions

    Callers decide when nothing references the bytes any more; this only deletes
    """
    if not _HASH.fullmatch(file_hash):
        raise ValueError(f"not a sha256 hex digest: {file_hash!r}")
    bucket = bucket_dir(scope, base)
    if not bucket.is_dir():
        return 0
    removed = 0
    for sidecar in bucket.glob(f"{file_hash}.*"):
        try:
            sidecar.unlink()
            removed += 1
        except OSError as e:
            logger.warning(f"could not remove sidecar {sidecar.name}: {e}")
    return removed


def sweep_orphans(known_hashes: Mapping[str, set[str]], base: Optional[Path] = None) -> dict[str, int]:
    """
    Delete sidecars whose hash no longer has an upload row in their bucket

    known_hashes maps a bucket directory name (a user id, or shared) to the hashes the registry still holds there
    Source-root sidecars have no registry rows by design and are never touched; per-file errors warn and continue
    """
    root = base if base is not None else base_dir()
    counts = {"kept": 0, "removed": 0, "errors": 0}
    if not root.is_dir():
        return counts

    for bucket in root.iterdir():
        if not bucket.is_dir() or bucket.name == SOURCE_ROOTS_DIR:
            continue
        keep = known_hashes.get(bucket.name, set())
        for sidecar in bucket.iterdir():
            if not sidecar.is_file():
                continue
            file_hash = sidecar.name.split(".", 1)[0]
            if file_hash in keep:
                counts["kept"] += 1
                continue
            try:
                sidecar.unlink()
                counts["removed"] += 1
            except OSError as e:
                counts["errors"] += 1
                logger.warning(f"sweep could not remove {bucket.name}/{sidecar.name}: {e}")
    return counts
