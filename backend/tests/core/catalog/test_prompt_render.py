"""
Tests for source_catalog.prompt_render
"""

from pathlib import Path

from app.model.schemas.source_catalog import (
    CatalogState,
    ObjectTypeMatch,
)
from app.services.source_catalog.indexes import build_indexes
from app.services.source_catalog.loader import load_catalog
from app.services.source_catalog.prompt_render import (
    deterministic_add_function_block,
    deterministic_registry_block,
    per_query_hints,
)


def _build(valid_catalog_path: Path):
    result = load_catalog(valid_catalog_path)
    assert result.catalog is not None
    return build_indexes(result.catalog)


def test_static_blocks_deterministic_same_input(valid_catalog_path: Path) -> None:
    idx_a = _build(valid_catalog_path)
    idx_b = _build(valid_catalog_path)
    assert deterministic_registry_block(idx_a) == deterministic_registry_block(idx_b)
    assert deterministic_add_function_block(idx_a) == deterministic_add_function_block(idx_b)


def test_static_blocks_invariant_to_count_changes(valid_catalog_path: Path, tmp_path: Path) -> None:
    """Mutating count-style fields must not change rendered bytes."""
    import json

    raw = json.loads(valid_catalog_path.read_text())
    raw["generated_at"] = "9999-12-31T00:00:00Z"
    raw["repos"]["mpmb_source"]["commit"] = "ffffffffffffffff"
    # Add a duplicate object (changes counts but not inventory)
    raw["objects"].append(dict(raw["objects"][0]))
    mutated = tmp_path / "mutated.json"
    mutated.write_text(json.dumps(raw))

    base = _build(valid_catalog_path)
    other = build_indexes(load_catalog(mutated).catalog)  # type: ignore[arg-type]

    assert deterministic_registry_block(base) == deterministic_registry_block(other)
    assert deterministic_add_function_block(base) == deterministic_add_function_block(other)


def test_static_blocks_change_on_new_registry(valid_catalog_path: Path, tmp_path: Path) -> None:
    """Adding a new registry name must change the registry block."""
    import json

    raw = json.loads(valid_catalog_path.read_text())
    raw["objects"].append(
        {
            "repo": "mpmb_source",
            "file": "f.js",
            "line": 99,
            "object_type": "SomeNewList",
            "object_key": "k",
            "assignment_kind": "bracket_object",
        }
    )
    mutated = tmp_path / "with_new.json"
    mutated.write_text(json.dumps(raw))

    base = _build(valid_catalog_path)
    other = build_indexes(load_catalog(mutated).catalog)  # type: ignore[arg-type]

    assert deterministic_registry_block(base) != deterministic_registry_block(other)
    assert "SomeNewList" in deterministic_registry_block(other)


def test_static_blocks_alphabetical_sort(valid_catalog_path: Path) -> None:
    block = deterministic_registry_block(_build(valid_catalog_path))
    # Lines containing each registry name must appear in alphabetical order.
    names_in_order = []
    for known in ("ClassSubList", "FeatsList", "SpellsList", "WeaponMasteriesList"):
        idx = block.find(known)
        assert idx >= 0
        names_in_order.append((idx, known))
    assert names_in_order == sorted(names_in_order)


def test_static_blocks_match_golden(valid_catalog_path: Path, fixtures_dir: Path) -> None:
    idx = _build(valid_catalog_path)
    expected_registry = (fixtures_dir / "expected/source_catalog/registry_block.txt").read_text()
    expected_add = (fixtures_dir / "expected/source_catalog/add_function_block.txt").read_text()
    assert deterministic_registry_block(idx) == expected_registry
    assert deterministic_add_function_block(idx) == expected_add


def test_per_query_hints_with_object_type_match(valid_catalog_path: Path) -> None:
    idx = _build(valid_catalog_path)
    hint = per_query_hints(
        object_type_match=ObjectTypeMatch(
            object_type="SpellsList",
            matched_via="code_identifier",
            matched_term="SpellsList",
        ),
        matched_symbols=[],
        coverage_warnings=tuple(idx.coverage_warnings),
        catalog_state=CatalogState.HEALTHY,
        injection_enabled=True,
    )
    assert hint is not None
    assert "SpellsList" in hint
    assert "//" in hint  # comment-style line


def test_per_query_hints_includes_coverage_warning(valid_catalog_path: Path) -> None:
    idx = _build(valid_catalog_path)
    hint = per_query_hints(
        object_type_match=None,
        matched_symbols=[],
        coverage_warnings=tuple(idx.coverage_warnings),
        catalog_state=CatalogState.HEALTHY,
        injection_enabled=True,
    )
    assert hint is not None
    assert "object_baseline" in hint or "Object coverage" in hint


def test_per_query_hints_disabled_by_setting() -> None:
    hint = per_query_hints(
        object_type_match=ObjectTypeMatch(
            object_type="SpellsList",
            matched_via="code_identifier",
            matched_term="SpellsList",
        ),
        matched_symbols=[],
        coverage_warnings=(),
        catalog_state=CatalogState.HEALTHY,
        injection_enabled=False,
    )
    assert hint is None


def test_per_query_hints_disabled_when_catalog_missing() -> None:
    hint = per_query_hints(
        object_type_match=None,
        matched_symbols=[],
        coverage_warnings=(),
        catalog_state=CatalogState.MISSING,
        injection_enabled=True,
    )
    assert hint is None


def test_per_query_hints_returns_none_when_no_signal() -> None:
    hint = per_query_hints(
        object_type_match=None,
        matched_symbols=[],
        coverage_warnings=(),
        catalog_state=CatalogState.HEALTHY,
        injection_enabled=True,
    )
    assert hint is None
