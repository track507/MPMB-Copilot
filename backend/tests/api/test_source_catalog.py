"""
Tests for POST /api/source-catalog/reload
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, valid_catalog_path: Path):
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "source_catalog_enabled", True)
    monkeypatch.setattr(settings_module.settings, "source_catalog_path", str(valid_catalog_path))
    from app.services.source_catalog import source_catalog_service

    source_catalog_service.load()
    from app.main import app

    return TestClient(app)


def test_reload_endpoint_success(client) -> None:
    response = client.post("/api/source-catalog/reload")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] in ("healthy", "stale")
    assert body["symbol_count"] > 0


def test_reload_returns_degraded_when_missing(monkeypatch, valid_catalog_path: Path) -> None:
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "source_catalog_enabled", True)
    monkeypatch.setattr(
        settings_module.settings,
        "source_catalog_path",
        str(valid_catalog_path.with_name("does_not_exist_for_reload_test.json")),
    )
    from app.services.source_catalog import source_catalog_service

    source_catalog_service.load()
    from app.main import app

    client = TestClient(app)

    response = client.post("/api/source-catalog/reload")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "missing"
    assert body["status"] == "degraded"
