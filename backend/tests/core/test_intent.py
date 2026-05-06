"""
Tests for catalog-backed intent classification (Layer 1 symbol detection)
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.intent import IntentClassifier, QueryIntent
from app.services.source_catalog import SourceCatalogService


@pytest.fixture
def healthy_service(monkeypatch, valid_catalog_path: Path) -> SourceCatalogService:
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "source_catalog_enabled", True)
    monkeypatch.setattr(settings_module.settings, "source_catalog_path", str(valid_catalog_path))
    monkeypatch.setattr(settings_module.settings, "intent_method", "rule")
    svc = SourceCatalogService()
    svc.load()
    return svc


@pytest.fixture
def missing_service(monkeypatch, tmp_path: Path) -> SourceCatalogService:
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "source_catalog_enabled", True)
    monkeypatch.setattr(settings_module.settings, "source_catalog_path", str(tmp_path / "nope.json"))
    monkeypatch.setattr(settings_module.settings, "intent_method", "rule")
    svc = SourceCatalogService()
    svc.load()
    return svc


def _classify(svc: SourceCatalogService, query: str) -> "tuple[QueryIntent, str]":
    """Layer 1 only - classifier with intent_method=rule and an unused embedding."""
    with patch("app.core.intent.source_catalog_service", svc):
        result = IntentClassifier().classify(query, query_embedding=[0.0] * 8)
    return result.primary, result.method


def test_layer_1_matches_catalog_registry(healthy_service: SourceCatalogService) -> None:
    intent, method = _classify(healthy_service, "Show me SpellsList examples")
    assert intent == QueryIntent.LOOKUP
    assert method == "symbol"


def test_layer_1_matches_catalog_add_function(healthy_service: SourceCatalogService) -> None:
    intent, method = _classify(healthy_service, "How do I use AddSubClass?")
    assert intent == QueryIntent.LOOKUP
    assert method == "symbol"


def test_layer_1_word_boundary(healthy_service: SourceCatalogService) -> None:
    """Substrings of catalog symbols must NOT trigger Layer 1."""
    intent, method = _classify(healthy_service, "MyClassListWrapper does X")
    # No catalog symbol matches; falls through to fallback in rule-only mode
    assert method != "symbol"


def test_error_context_override_to_debug(healthy_service: SourceCatalogService) -> None:
    intent, method = _classify(healthy_service, "SpellsList is broken and won't load")
    assert intent == QueryIntent.DEBUG
    assert method == "symbol"


def test_layer_1_skipped_when_catalog_missing(missing_service: SourceCatalogService) -> None:
    intent, method = _classify(missing_service, "Tell me about SpellsList")
    assert method != "symbol"  # no catalog -> no Layer 1


def test_layer_1_skipped_when_catalog_malformed(monkeypatch, tmp_path: Path) -> None:
    from app import settings as settings_module

    bad = tmp_path / "bad.json"
    bad.write_text("{")
    monkeypatch.setattr(settings_module.settings, "source_catalog_enabled", True)
    monkeypatch.setattr(settings_module.settings, "source_catalog_path", str(bad))
    monkeypatch.setattr(settings_module.settings, "intent_method", "rule")
    svc = SourceCatalogService()
    svc.load()
    intent, method = _classify(svc, "Tell me about SpellsList")
    assert method != "symbol"


def test_intent_method_rule_only_with_missing_catalog(missing_service: SourceCatalogService) -> None:
    """rule-only mode + missing catalog -> graceful HOW_TO fallback, no exception."""
    intent, method = _classify(missing_service, "How do I add a feat?")
    assert intent == QueryIntent.HOW_TO
    assert method in ("fallback", "embedding")
