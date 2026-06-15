import pytest

from app.core import embedding_catalog as ec


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "openai_api_key", None)
    yield


def test_pinned_local_models_are_ready():
    bge = ec.get_entry("fastembed", "BAAI/bge-small-en-v1.5")
    assert bge is not None
    assert bge.dimension == 384
    assert ec.status_for(bge) == "ready"  # local, no key needed


def test_openai_entry_needs_key_when_absent():
    e = ec.get_entry("openai", "text-embedding-3-small")
    assert e.dimension == 1536
    assert ec.status_for(e) == "needs_key"


def test_stub_provider_is_installable_when_dep_missing():
    e = ec.get_entry("cohere", "embed-multilingual-v3.0")
    assert e is not None
    assert ec.status_for(e) == "installable"  # cohere package not installed


def test_dimension_for_falls_back_for_unknown():
    assert ec.dimension_for("fastembed", "BAAI/bge-small-en-v1.5") == 384
    assert ec.dimension_for("fastembed", "unknown-model") == 384  # falls back to default entry


def test_e5_carries_prefixes():
    e = ec.get_entry("fastembed", "intfloat/multilingual-e5-large")
    assert e.query_prefix == "query: "
    assert e.doc_prefix == "passage: "
    assert e.multilingual is True


@pytest.mark.asyncio
async def test_embedding_models_endpoint_serializes(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import settings as settings_api
    from app.config import config

    monkeypatch.setattr(config, "openai_api_key", None)
    app = FastAPI()
    app.include_router(settings_api.router)
    client = TestClient(app)

    resp = client.get("/embedding-models")
    assert resp.status_code == 200
    body = resp.json()
    assert "models" in body and "current" in body
    entry = body["models"][0]
    assert set(entry) == {"provider", "id", "label", "dimension", "multilingual", "pinned", "status"}
