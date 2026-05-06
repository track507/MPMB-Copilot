from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.query_analysis import analyze_query
from app.services.source_catalog import SourceCatalogService


@pytest.mark.parametrize(
    "query,expected",
    [
        # Exact identifier matches
        ("How do I use ClassList?", "ClassList"),
        ("What about ClassSubList?", "ClassSubList"),
        ("Show me BackgroundFeatureList syntax", "BackgroundFeatureList"),
        ("How do BackgroundList entries work?", "BackgroundList"),
        ("Tell me about SpellsList", "SpellsList"),
        ("How does WeaponMasteriesList work?", "WeaponMasteriesList"),
        ("Show DefaultEvalsList syntax", "DefaultEvalsList"),
        ("How do I add artisan tools?", "ToolsList"),
        ("How do I add psionic disciplines?", "PsionicsList"),
        # Prefix collisions - the longer name must win when both are present
        ("How does ClassSubList differ from ClassList?", "ClassSubList"),
        # Typo / non-existent identifier must not falsely match a prefix
        ("What about SubClassList?", None),
        # Natural language falls through to keyword matching
        ("How do I add a subclass?", "ClassSubList"),
        ("How do I add a spell?", "SpellsList"),
        ("Show me feats", "FeatsList"),
        # Bare "source" is intentionally not mapped
        ("Where is the source code?", None),
    ],
)
def test_object_type_inference(
    healthy_qa_service: SourceCatalogService,
    query: str,
    expected: str | None,
) -> None:
    assert _analyze(healthy_qa_service, query).object_type == expected


@pytest.mark.parametrize(
    "query,expected",
    [
        ("How do I add a 2024 spell?", "2024"),
        ("Show me the 2014 PHB rules", "2014"),
        ("What's new in OneD&D?", "2024"),
        ("Explain the classic edition", "2014"),
        ("How do I add a spell?", None),  # No edition signal
    ],
)
def test_edition_inference(query: str, expected: str | None) -> None:
    assert analyze_query(query).edition == expected


@pytest.fixture
def healthy_qa_service(monkeypatch, valid_catalog_path: Path) -> SourceCatalogService:
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "source_catalog_enabled", True)
    monkeypatch.setattr(settings_module.settings, "source_catalog_path", str(valid_catalog_path))
    svc = SourceCatalogService()
    svc.load()
    return svc


@pytest.fixture
def missing_qa_service(monkeypatch, tmp_path: Path) -> SourceCatalogService:
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "source_catalog_enabled", True)
    monkeypatch.setattr(settings_module.settings, "source_catalog_path", str(tmp_path / "nope.json"))
    svc = SourceCatalogService()
    svc.load()
    return svc


def _analyze(svc: SourceCatalogService, query: str):
    with patch("app.core.query_analysis.source_catalog_service", svc):
        return analyze_query(query)


def test_catalog_registry_literal_match(healthy_qa_service) -> None:
    a = _analyze(healthy_qa_service, "How does SpellsList work?")
    assert a.object_type == "SpellsList"


def test_nl_alias_for_unknown_registry(healthy_qa_service) -> None:
    """RaceSubList is NOT in the synthetic catalog's registries.
    The 'subrace' NL alias must still resolve via the alias map fallback."""
    a = _analyze(healthy_qa_service, "Tell me about subraces")
    assert a.object_type == "RaceSubList"


def test_nl_alias_when_catalog_missing(missing_qa_service) -> None:
    a = _analyze(missing_qa_service, "How do I add a spell?")
    assert a.object_type == "SpellsList"


def test_longest_first_classsublist_vs_classlist(healthy_qa_service) -> None:
    a = _analyze(healthy_qa_service, "ClassSubList question")
    assert a.object_type == "ClassSubList"


def test_no_match_unknown_query(healthy_qa_service) -> None:
    a = _analyze(healthy_qa_service, "weather forecast")
    assert a.object_type is None


def test_edition_inference_unchanged(healthy_qa_service) -> None:
    a = _analyze(healthy_qa_service, "How do I add a 2024 spell?")
    assert a.edition == "2024"
