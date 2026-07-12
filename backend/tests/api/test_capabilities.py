from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(monkeypatch):
    from app.api import settings as settings_api
    from app.api.deps import Principal, current_principal
    from app.core import model_catalog, registry

    async def _fake_models():
        return {"anthropic": [], "openai": [], "ollama": []}

    monkeypatch.setattr(model_catalog, "get_model_catalog", _fake_models)
    monkeypatch.setattr(registry, "_REGISTRY", {})  # ? force rebuild so the stub fetch is used

    app = FastAPI()
    # ? Mini-app carries no session cookie; require_admin is real now, so override the principal like conftest does for main.app
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="default", role="admin")
    app.include_router(settings_api.router)
    return TestClient(app)


def test_capabilities_endpoint_shape(monkeypatch):
    client = _client(monkeypatch)
    resp = client.get("/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"generation", "embedding", "rerank", "vector_store", "auth"}
    assert set(body["rerank"]) == {"label", "kind", "entries", "current"}
    assert "model" in body["rerank"]["current"]


def test_patch_settings_accepts_rerank_fields(monkeypatch):
    from app.settings import settings

    captured: dict = {}
    monkeypatch.setattr(settings, "update", lambda **kw: captured.update(kw))  # ? no disk writes / no state leak

    client = _client(monkeypatch)
    resp = client.patch("/settings", json={"rerank_enabled": True, "rerank_model": "BAAI/bge-reranker-base"})
    assert resp.status_code == 200
    assert captured == {"rerank_enabled": True, "rerank_model": "BAAI/bge-reranker-base"}


def test_settings_read_requires_admin():
    from fastapi.testclient import TestClient

    from app.api.deps import Principal, current_principal
    from app.main import app

    app.dependency_overrides[current_principal] = lambda: Principal(user_id="u1", role="user")
    try:
        assert TestClient(app, raise_server_exceptions=False).get("/api/settings").status_code == 403
    finally:
        app.dependency_overrides.pop(current_principal, None)
