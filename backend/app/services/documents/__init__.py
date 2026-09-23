"""
Document read path: turns uploaded or hand-placed documents into text the file tools can read and search

Imports nothing from the database layer, so the tool layer can depend on it without reaching persistence
"""

from app.services.documents.cache import CachedDocument
from app.services.documents.errors import DocumentError
from app.services.documents.protocol import CacheScope, DocumentExtractor, Extraction, OutlineEntry, normalize
from app.services.documents.registry import EXTRACTABLE_EXTENSIONS, is_extractable
from app.services.documents.service import cached_summary, ensure_extracted, lookup, release

__all__ = [
    "EXTRACTABLE_EXTENSIONS",
    "CacheScope",
    "CachedDocument",
    "DocumentError",
    "DocumentExtractor",
    "Extraction",
    "OutlineEntry",
    "cached_summary",
    "ensure_extracted",
    "is_extractable",
    "lookup",
    "normalize",
    "release",
]
