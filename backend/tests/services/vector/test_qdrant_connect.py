import pytest

from app.config import config
from app.services.vector import qdrant as qdrant_mod
from app.services.vector.qdrant import QdrantStore


@pytest.fixture
def created(monkeypatch):
    seen: list[dict] = []

    class _Client:
        def __init__(self, **kwargs):
            seen.append(kwargs)

        def get_collections(self):
            raise ConnectionError("no server in tests")

    monkeypatch.setattr(qdrant_mod, "QdrantClient", _Client)
    return seen


@pytest.mark.asyncio
async def test_connect_sends_the_key_from_the_secrets_port(monkeypatch, created):
    monkeypatch.setattr(config, "qdrant_api_key", "qk-test", raising=False)
    monkeypatch.setattr(config, "qdrant_https", False, raising=False)
    assert await QdrantStore().connect() is False
    assert created[0]["api_key"] == "qk-test"
    assert created[0]["https"] is False


@pytest.mark.asyncio
async def test_connect_without_a_key_sends_none(monkeypatch, created):
    monkeypatch.setattr(config, "qdrant_api_key", None, raising=False)
    await QdrantStore().connect()
    assert created[0]["api_key"] is None
