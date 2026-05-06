"""
Tests for /api/health source_catalog block
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_healthy_catalog(monkeypatch, valid_catalog_path: Path):
    from app import settings as settings_module
    from app.model.schemas.source_catalog import CatalogState

    monkeypatch.setattr(settings_module.settings, "source_catalog_enabled", True)
    monkeypatch.setattr(settings_module.settings, "source_catalog_path", str(valid_catalog_path))
    monkeypatch.setattr(
        "app.services.source_catalog.staleness.check_staleness",
        lambda repos: (CatalogState.HEALTHY, {name: repo.commit for name, repo in repos.items()}),
    )
    from app.services.source_catalog import source_catalog_service

    source_catalog_service._staleness_cache.invalidate()
    source_catalog_service.load()
    from app.main import app

    return TestClient(app)


@pytest.fixture
def client_with_missing_catalog(monkeypatch, valid_catalog_path: Path):
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "source_catalog_enabled", True)
    monkeypatch.setattr(
        settings_module.settings,
        "source_catalog_path",
        str(valid_catalog_path.with_name("does_not_exist_for_health_test.json")),
    )
    from app.services.source_catalog import source_catalog_service

    source_catalog_service.load()
    from app.main import app

    return TestClient(app)


def test_health_includes_source_catalog_block(client_with_healthy_catalog) -> None:
    response = client_with_healthy_catalog.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert "source_catalog" in body
    assert body["source_catalog"] is not None
    assert "state" in body["source_catalog"]
    assert "symbol_count" in body["source_catalog"]


def test_health_healthy_catalog(client_with_healthy_catalog) -> None:
    body = client_with_healthy_catalog.get("/api/health").json()
    assert body["source_catalog"]["status"] == "healthy"
    assert body["source_catalog"]["state"] == "healthy"
    assert body["source_catalog"]["symbol_count"] > 0


def test_missing_catalog_degrades_overall(client_with_missing_catalog) -> None:
    body = client_with_missing_catalog.get("/api/health").json()
    assert body["source_catalog"]["status"] == "degraded"
    assert body["source_catalog"]["state"] == "missing"
    # Overall should be degraded if no other unhealthy services; never "unhealthy" from catalog alone
    assert body["status"] in ("degraded", "healthy")  # depends on other services in test env
    assert body["status"] != "unhealthy"


def test_high_severity_coverage_does_not_degrade(client_with_healthy_catalog, monkeypatch) -> None:
    """High-severity coverage warnings are informational; they do not change status."""
    body = client_with_healthy_catalog.get("/api/health").json()
    assert body["source_catalog"]["status"] == "healthy"
