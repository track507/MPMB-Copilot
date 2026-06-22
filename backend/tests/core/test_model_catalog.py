import pytest

from app.core import model_catalog
from app.core.model_catalog import (
    ANTHROPIC_CURATED,
    OPENAI_CURATED,
    effort_levels_for,
    get_model_catalog,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    model_catalog._cache.clear()
    yield
    model_catalog._cache.clear()


@pytest.mark.asyncio
async def test_catalog_falls_back_to_curated_without_keys(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "anthropic_api_key", None)
    monkeypatch.setattr(config, "openai_api_key", None)

    catalog = await get_model_catalog()

    assert [m["id"] for m in catalog["anthropic"]] == [o.id for o in ANTHROPIC_CURATED]
    assert [m["id"] for m in catalog["openai"]] == [o.id for o in OPENAI_CURATED]
    assert catalog["ollama"] == []


@pytest.mark.asyncio
async def test_catalog_entries_have_id_and_label(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "anthropic_api_key", None)
    monkeypatch.setattr(config, "openai_api_key", None)

    catalog = await get_model_catalog()

    for entry in [*catalog["anthropic"], *catalog["openai"]]:
        assert set(entry) == {"id", "label", "effort"}
        assert entry["id"] and entry["label"]
        assert isinstance(entry["effort"], list)


@pytest.mark.asyncio
async def test_catalog_carries_effort_levels(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "anthropic_api_key", None)
    monkeypatch.setattr(config, "openai_api_key", None)

    catalog = await get_model_catalog()
    by_id = {m["id"]: m for m in catalog["anthropic"]}

    assert by_id["claude-opus-4-8"]["effort"] == ["low", "medium", "high", "xhigh", "max"]
    # ! Haiku does not support effort - empty list hides the control
    assert by_id["claude-haiku-4-5"]["effort"] == []
    # OpenAI uses its own scale: no Anthropic-only 'max', and 'none' is reasoning-off not a tier
    for m in catalog["openai"]:
        assert "max" not in m["effort"]
        assert "none" not in m["effort"]
        assert {"low", "medium", "high"}.issubset(m["effort"])


def test_effort_levels_for_when_cache_cold():
    # Anthropic falls back to the static table
    assert effort_levels_for("anthropic", "claude-opus-4-8") == ("low", "medium", "high", "xhigh", "max")
    assert effort_levels_for("anthropic", "claude-haiku-4-5") == ()
    assert effort_levels_for("anthropic", "totally-unknown-model") == ()
    # OpenAI is profile-driven: reasoning models get the scale, non-reasoning get none
    openai_levels = effort_levels_for("openai", "gpt-5.4")
    assert {"low", "medium", "high"}.issubset(openai_levels)
    assert "max" not in openai_levels and "none" not in openai_levels
    assert effort_levels_for("openai", "gpt-4o") == ()
    assert effort_levels_for("ollama", "llama3") == ()


def test_effort_levels_for_prefers_warm_cache(monkeypatch):
    from app.core.model_catalog import ModelOption

    monkeypatch.setitem(
        model_catalog._cache,
        "anthropic",
        (1.0e18, [ModelOption("claude-opus-4-8", "Claude Opus 4.8", ("low", "high"))]),
    )
    # ? Cached (live-derived) levels win over the static table
    assert effort_levels_for("anthropic", "claude-opus-4-8") == ("low", "high")


@pytest.mark.asyncio
async def test_anthropic_fetch_failure_falls_back(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "anthropic_api_key", "sk-test")

    class Boom:
        def __init__(self, **kwargs):
            raise RuntimeError("network down")

    monkeypatch.setattr("anthropic.AsyncAnthropic", Boom)

    options = await model_catalog._fetch_anthropic()
    assert [o.id for o in options] == [o.id for o in ANTHROPIC_CURATED]
