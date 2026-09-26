"""
An immutable view of the source catalog, handed to the domain once per turn

The domain reads a catalog; it does not own one
Loading a file, watching its mtime and shelling out to git are adapter concerns, so `services/source_catalog` keeps those and produces one of these instead

"""

from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional, Protocol

from app.core.catalog.indexes import Indexes
from app.model.schemas.source_catalog import CatalogState, CoverageWarning, ObjectTypeMatch, SymbolEntry

_NO_SYMBOLS: Mapping[str, SymbolEntry] = {}


@dataclass(frozen=True)
class CatalogSnapshot:
    indexes: Optional[Indexes] = None
    state: CatalogState = CatalogState.MISSING
    registry_block: str = ""
    add_function_block: str = ""
    coverage_warning_list: tuple[CoverageWarning, ...] = field(default_factory=tuple)

    @property
    def has_data(self) -> bool:
        # ? STALE still answers questions; only MISSING and MALFORMED mean there is nothing to read
        return self.state in (CatalogState.HEALTHY, CatalogState.STALE) and self.indexes is not None

    @property
    def symbols(self) -> Mapping[str, SymbolEntry]:
        return self.indexes.symbols if self.indexes is not None else _NO_SYMBOLS

    @property
    def registry_names(self) -> tuple[str, ...]:
        return self.indexes.registry_names if self.indexes is not None else ()

    def find_object_type(self, query: str) -> Optional[ObjectTypeMatch]:
        return self.indexes.find_object_type(query) if self.indexes is not None else None

    def static_prompt_blocks(self) -> tuple[str, str]:
        return self.registry_block, self.add_function_block


EMPTY_CATALOG = CatalogSnapshot()


class CatalogProvider(Protocol):
    def __call__(self) -> CatalogSnapshot: ...


CatalogProviderFn = Callable[[], CatalogSnapshot]
