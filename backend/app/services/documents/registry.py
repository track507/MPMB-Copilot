"""
Extension to extractor lookup

A locator keyed by file extension, so each adapter is imported only when a file of its format is opened
"""

import json
import time
from typing import Optional

from app.services.documents.protocol import DocumentExtractor
from app.settings import settings

# ! Must widen in lockstep with UPLOAD_EXTENSIONS and the tools' ALLOWED_EXTENSIONS, one format per adapter change
# ? Accepting an upload nothing can read recreates the dead end this registry exists to close
EXTRACTABLE_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".csv", ".tsv"})

# * The id names the sidecar on disk, so it must stay stable for a given adapter
_EXTRACTOR_IDS: dict[str, str] = {".pdf": "pdf", ".csv": "csv", ".tsv": "csv"}

_AVAILABILITY_TTL_SECONDS = 60.0

_extractors: dict[str, DocumentExtractor] = {}
_availability: dict[tuple[str, str], tuple[float, Optional[str]]] = {}


def is_extractable(extension: str) -> bool:
    return extension.lower() in EXTRACTABLE_EXTENSIONS


def extractor_id(extension: str) -> Optional[str]:
    return _EXTRACTOR_IDS.get(extension.lower())


def extractor_for(extension: str) -> Optional[DocumentExtractor]:
    """The adapter for an extension, imported on first use, or None when no adapter reads it"""
    ext = extension.lower()
    known = _extractors.get(ext)
    if known is not None:
        return known

    extractor: DocumentExtractor
    if ext == ".pdf":
        from app.services.documents.ops.pdf import PdfExtractor

        extractor = PdfExtractor()
    elif ext in (".csv", ".tsv"):
        from app.services.documents.ops.csv import CsvExtractor

        extractor = CsvExtractor()
    else:
        return None

    _extractors[ext] = extractor
    return extractor


def availability(extension: str) -> Optional[str]:
    """
    None when the extension's adapter is usable, otherwise the reason

    Cached briefly because a probe may shell out, keyed on the documents settings so toggling one re-probes at once
    """
    extractor = extractor_for(extension)
    if extractor is None:
        return f"no reader for {extension.lower()} files"

    key = (extension.lower(), json.dumps(settings.documents, sort_keys=True, default=str))
    now = time.monotonic()
    cached = _availability.get(key)
    if cached is not None and now - cached[0] < _AVAILABILITY_TTL_SECONDS:
        return cached[1]

    reason = extractor.check_availability()
    _availability[key] = (now, reason)
    return reason
