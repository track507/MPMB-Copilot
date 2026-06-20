import pytest

from app.core import registry
from app.core.registry import Capability, CapabilitySpec


@pytest.fixture
def fresh_registry(monkeypatch):
    # ? isolate the module-level registry per test
    monkeypatch.setattr(registry, "_REGISTRY", {})
    yield registry


def test_register_and_all_specs(fresh_registry):
    spec = CapabilitySpec(
        key=Capability.embedding,
        label="E",
        kind="curated",
        entries=lambda: [{"id": "x"}],
        current=lambda: {"model": "x"},
    )
    fresh_registry.register(spec)
    assert fresh_registry.get_spec(Capability.embedding) is spec
    assert [s.key for s in fresh_registry.all_specs()] == [Capability.embedding]


@pytest.mark.asyncio
async def test_serialize_all_includes_four_builtins(fresh_registry, monkeypatch):
    async def _fake_models():
        return {"anthropic": [{"id": "claude", "label": "Claude", "effort": []}], "openai": [], "ollama": []}

    from app.core import model_catalog

    monkeypatch.setattr(model_catalog, "get_model_catalog", _fake_models)

    out = await fresh_registry.serialize_all()
    assert set(out) == {"generation", "embedding", "rerank", "vector_store"}
    for cap in out.values():
        assert set(cap) == {"label", "kind", "entries", "current"}
    # generation entries came from the awaited live-fetch stub
    assert out["generation"]["entries"]["anthropic"][0]["id"] == "claude"
    # curated capabilities carry status-bearing rows
    assert out["embedding"]["entries"][0]["status"] in {"ready", "needs_key", "installable"}


@pytest.mark.asyncio
async def test_serialize_all_current_reflects_settings(fresh_registry, monkeypatch):
    from app.core import model_catalog
    from app.settings import settings

    async def _fake_models():
        return {"anthropic": [], "openai": [], "ollama": []}

    monkeypatch.setattr(model_catalog, "get_model_catalog", _fake_models)
    monkeypatch.setattr(settings, "rerank_model", "BAAI/bge-reranker-base")
    monkeypatch.setattr(settings, "rerank_enabled", True)

    out = await fresh_registry.serialize_all()
    assert out["rerank"]["current"]["model"] == "BAAI/bge-reranker-base"
    assert out["rerank"]["current"]["enabled"] is True
