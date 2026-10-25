from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.settings import settings


def test_the_catalog_path_cannot_be_set_over_http(monkeypatch):
    update = Mock()
    monkeypatch.setattr(settings, "update", update)
    from app.main import app

    response = TestClient(app).patch("/api/settings", json={"source_catalog_path": "\\\\attacker\\share\\x.json"})
    assert response.status_code == 400
    update.assert_not_called()
