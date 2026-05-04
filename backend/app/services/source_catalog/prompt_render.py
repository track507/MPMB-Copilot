"""Deterministic rendering of catalog data into prompt sections.

The static-block functions produce cache-stable text: same catalog
*inventory* → identical bytes, regardless of counts or volatile fields.
"""

from typing import Optional

from app.model.schemas.source_catalog import (
    CatalogState,
    CoverageWarning,
    ObjectTypeMatch,
    SymbolEntry,
    SymbolKind,
)
from app.services.source_catalog.indexes import Indexes

_REGISTRY_HEADER = "MPMB OBJECT TYPES you can create or modify:"
_ADD_FN_HEADER = "MPMB ADD FUNCTIONS (alternative to direct object assignment):"

# v1: catalog-only rendering. No hardcoded role/signature maps. The LLM
# infers role/signature from the registry/function name + RAG context
# (syntax templates, examples). If we later want labeled prose hints,
# pull them from a catalog-derived source — never hand-maintained.


def deterministic_registry_block(indexes: Indexes) -> str:
    """Cache-stable registry list. Sorted alphabetically by name."""
    lines: list[str] = [_REGISTRY_HEADER]
    registries = sorted(name for name, sym in indexes.symbols.items() if sym.kind == SymbolKind.REGISTRY)
    for name in registries:
        lines.append(f'- {name}["key"] = {{ ... }}')
    return "\n".join(lines)


def deterministic_add_function_block(indexes: Indexes) -> str:
    """Cache-stable Add* function list. Sorted alphabetically by name."""
    lines: list[str] = [_ADD_FN_HEADER]
    fns = sorted(name for name, sym in indexes.symbols.items() if sym.kind == SymbolKind.ADD_DECLARATION)
    for name in fns:
        lines.append(f"- {name}(...)")
    return "\n".join(lines)


def per_query_hints(
    *,
    object_type_match: Optional[ObjectTypeMatch],
    matched_symbols: list[SymbolEntry],
    coverage_warnings: tuple[CoverageWarning, ...],
    catalog_state: CatalogState,
    injection_enabled: bool,
) -> Optional[str]:
    """Build 1-4 short comment lines for the user-prompt context block.

    Returns None when:
        - injection_enabled is False
        - catalog_state in {MISSING, MALFORMED}
        - no signal worth surfacing
    Output is deterministic (sorted lines).
    """
    if not injection_enabled:
        return None
    if catalog_state in (CatalogState.MISSING, CatalogState.MALFORMED):
        return None

    hints: list[str] = []

    if object_type_match is not None:
        hints.append(
            f"// Resolved object type: {object_type_match.object_type} (matched via {object_type_match.matched_via})"
        )

    for sym in sorted(matched_symbols, key=lambda s: s.name):
        hints.append(
            f"// Catalog symbol: {sym.name} ({sym.kind.value}, "
            f"{sym.occurrence_count} occurrences across {len(sym.repos)} repo(s))"
        )

    # Surface only the highest-severity warning relevant to the matched object_type
    # (or top warning overall if no object_type). Cap at one to keep token cost low.
    if coverage_warnings:
        top = coverage_warnings[0]
        hints.append(
            f"// Coverage warning [{top.severity}]: {top.key} — "
            f"parser misses {top.missed}/{top.target}; verify with mpmb_grep before generating"
        )

    if catalog_state == CatalogState.STALE:
        hints.insert(0, "// Catalog is STALE (analyzer captured commits drift from live repos)")

    if not hints:
        return None
    return "\n".join(hints)
