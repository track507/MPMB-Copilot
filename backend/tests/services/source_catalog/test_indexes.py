"""
Tests for source_catalog.indexes
"""

from pathlib import Path

from app.model.schemas.source_catalog import SymbolKind
from app.services.source_catalog.indexes import build_indexes
from app.services.source_catalog.loader import load_catalog


def _load_indexes(path: Path):
    result = load_catalog(path)
    assert result.catalog is not None
    return build_indexes(result.catalog)


def test_symbol_index_contains_registries(valid_catalog_path: Path) -> None:
    idx = _load_indexes(valid_catalog_path)
    for name in ("SpellsList", "FeatsList", "ClassSubList", "WeaponMasteriesList"):
        assert name in idx.symbols, f"missing registry: {name}"
        assert idx.symbols[name].kind == SymbolKind.REGISTRY


def test_symbol_index_contains_mapped_add_calls(valid_catalog_path: Path) -> None:
    idx = _load_indexes(valid_catalog_path)
    for name in ("AddSubClass", "AddRacialVariant"):
        assert name in idx.symbols, f"missing add call: {name}"
        assert idx.symbols[name].kind == SymbolKind.ADD_DECLARATION


def test_symbol_index_excludes_unmapped_add_calls(valid_catalog_path: Path) -> None:
    idx = _load_indexes(valid_catalog_path)
    assert "AddString" not in idx.symbols  # mapped=false


def test_symbol_index_excludes_engine_functions(valid_catalog_path: Path) -> None:
    idx = _load_indexes(valid_catalog_path)
    assert "ParseSpell" not in idx.symbols  # engine fn deliberately excluded in v1


def test_symbol_index_excludes_source_keys(valid_catalog_path: Path) -> None:
    idx = _load_indexes(valid_catalog_path)
    for key in ("P", "P24", "SRD"):
        assert key not in idx.symbols


def test_symbol_index_carries_repos(valid_catalog_path: Path) -> None:
    idx = _load_indexes(valid_catalog_path)
    spells = idx.symbols["SpellsList"]
    assert spells.repos == ["mpmb_source"]
    masteries = idx.symbols["WeaponMasteriesList"]
    assert masteries.repos == ["mpmb_source_2024"]


def test_registry_names_sorted_longest_first(valid_catalog_path: Path) -> None:
    idx = _load_indexes(valid_catalog_path)
    names = idx.registry_names
    assert names == tuple(sorted(names, key=len, reverse=True))
    # ClassSubList must precede ClassList if both present
    assert "WeaponMasteriesList" in names
    assert "ClassSubList" in names


def test_find_object_type_exact_registry_match(valid_catalog_path: Path) -> None:
    idx = _load_indexes(valid_catalog_path)
    match = idx.find_object_type("How does SpellsList work?")
    assert match is not None
    assert match.object_type == "SpellsList"
    assert match.matched_via == "code_identifier"


def test_find_object_type_word_boundary(valid_catalog_path: Path) -> None:
    idx = _load_indexes(valid_catalog_path)
    assert idx.find_object_type("MyClassListWrapper") is None  # no false-positive


def test_find_object_type_longest_first_wins(valid_catalog_path: Path) -> None:
    idx = _load_indexes(valid_catalog_path)
    match = idx.find_object_type("ClassSubList question")
    assert match is not None
    assert match.object_type == "ClassSubList"  # not falsely captured by ClassList


def test_find_object_type_returns_none_for_aliases(valid_catalog_path: Path) -> None:
    idx = _load_indexes(valid_catalog_path)
    # "spell" is an NL alias handled in query_analysis, not catalog
    assert idx.find_object_type("How do I add a spell?") is None


def test_coverage_severity_summary(valid_catalog_path: Path) -> None:
    idx = _load_indexes(valid_catalog_path)
    assert idx.coverage_severity_summary == {"high": 0, "medium": 1, "low": 0}
