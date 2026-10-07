from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


def _state(monkeypatch, *, warm: bool, db: bool, migrated: bool = True) -> None:
    from app.main import app

    monkeypatch.setattr(app.state, "warm", warm, raising=False)
    monkeypatch.setattr(app.state, "migrated", migrated, raising=False)
    monkeypatch.setattr("app.api.health.db", SimpleNamespace(is_connected=db))


def test_cold_models_are_not_ready(client, monkeypatch):
    _state(monkeypatch, warm=False, db=True)

    resp = client.get("/api/ready")

    assert resp.status_code == 503
    assert resp.json() == {"ready": False, "models": False, "database": True}


def test_a_failed_migration_is_not_ready(client, monkeypatch):
    _state(monkeypatch, warm=True, db=True, migrated=False)

    assert client.get("/api/ready").status_code == 503


def test_warm_models_with_a_database_are_ready(client, monkeypatch):
    _state(monkeypatch, warm=True, db=True)

    assert client.get("/api/ready").status_code == 200


def test_warm_models_without_a_database_are_not_ready(client, monkeypatch):
    _state(monkeypatch, warm=True, db=False)

    assert client.get("/api/ready").status_code == 503


def test_liveness_answers_while_not_ready(client, monkeypatch):
    _state(monkeypatch, warm=False, db=False)

    assert client.get("/api/ping").status_code == 200
