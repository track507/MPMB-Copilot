"""
The catalog's pure half: derived indexes, prompt rendering, and the per-turn snapshot the domain reads

Loading, mtime watching and git provenance stay in services/source_catalog, which builds these and hands one over
"""

from app.core.catalog.indexes import Indexes, build_indexes
from app.core.catalog.prompt_render import (
    deterministic_add_function_block,
    deterministic_registry_block,
    per_query_hints,
)
from app.core.catalog.snapshot import EMPTY_CATALOG, CatalogProvider, CatalogProviderFn, CatalogSnapshot

__all__ = [
    "EMPTY_CATALOG",
    "CatalogProvider",
    "CatalogProviderFn",
    "CatalogSnapshot",
    "Indexes",
    "build_indexes",
    "deterministic_add_function_block",
    "deterministic_registry_block",
    "per_query_hints",
]
