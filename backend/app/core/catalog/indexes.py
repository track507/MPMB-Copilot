"""
Derived in-memory indexes built from a CatalogModel
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from app.model.schemas.source_catalog import (
    CatalogModel,
    CoverageWarning,
    ObjectTypeMatch,
    SymbolEntry,
    SymbolKind,
)


@dataclass(frozen=True)
class Indexes:
    symbols: dict[str, SymbolEntry] = field(default_factory=dict)
    registry_names: tuple[str, ...] = ()
    coverage_warnings: tuple[CoverageWarning, ...] = ()
    coverage_severity_summary: dict[str, int] = field(default_factory=dict)
    object_count: int = 0
    symbol_count: int = 0

    def find_object_type(self, query: str) -> Optional[ObjectTypeMatch]:
        """Word-boundary, longest-first match against catalog registry names."""
        for name in self.registry_names:
            if re.search(rf"\b{re.escape(name)}\b", query):
                return ObjectTypeMatch(
                    object_type=name,
                    matched_via="code_identifier",
                    matched_term=name,
                )
        return None


def build_indexes(catalog: CatalogModel) -> Indexes:
    """Build all derived structures from a parsed catalog."""

    # Symbol index: registries + mapped Add* declarations only (v1 scope)
    registry_repos: dict[str, set[str]] = defaultdict(set)
    registry_counts: dict[str, int] = defaultdict(int)
    for obj in catalog.objects:
        registry_repos[obj.object_type].add(obj.repo)
        registry_counts[obj.object_type] += 1

    add_call_repos: dict[str, set[str]] = defaultdict(set)
    add_call_counts: dict[str, int] = defaultdict(int)
    for call in catalog.add_calls:
        if not call.mapped:
            continue
        add_call_repos[call.function_name].add(call.repo)
        add_call_counts[call.function_name] += 1

    symbols: dict[str, SymbolEntry] = {}
    for name, repos in registry_repos.items():
        symbols[name] = SymbolEntry(
            name=name,
            kind=SymbolKind.REGISTRY,
            occurrence_count=registry_counts[name],
            repos=sorted(repos),
        )
    for name, repos in add_call_repos.items():
        symbols[name] = SymbolEntry(
            name=name,
            kind=SymbolKind.ADD_DECLARATION,
            occurrence_count=add_call_counts[name],
            repos=sorted(repos),
        )

    # Registry names sorted longest-first for word-boundary scanning
    registry_names = tuple(sorted(registry_repos.keys(), key=lambda n: (-len(n), n)))

    # Coverage warnings sorted by severity (high → medium → low) then missed desc
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    coverage_sorted = tuple(
        sorted(
            catalog.coverage_metrics,
            key=lambda w: (severity_rank.get(w.severity, 99), -w.missed),
        )
    )
    severity_summary = {"high": 0, "medium": 0, "low": 0}
    for w in catalog.coverage_metrics:
        if w.severity in severity_summary:
            severity_summary[w.severity] += 1

    return Indexes(
        symbols=symbols,
        registry_names=registry_names,
        coverage_warnings=coverage_sorted,
        coverage_severity_summary=severity_summary,
        object_count=len(catalog.objects),
        symbol_count=len(symbols),
    )
