from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import title_generator


def test_sanitize_strips_quotes_and_punctuation():
    assert title_generator._sanitize('"Add a new spell to PHB."') == "Add a new spell to PHB"
    assert title_generator._sanitize("'AbilityScores object body'") == "AbilityScores object body"
    assert title_generator._sanitize("Spell list lookup!") == "Spell list lookup"


def test_sanitize_caps_length():
    long_title = "x" * 200
    out = title_generator._sanitize(long_title)
    assert len(out) <= title_generator._MAX_TITLE_CHARS + 1  # +1 for ellipsis
    assert out.endswith("…")


def test_fallback_title_truncates_long_message():
    msg = "Show me the full body of the AbilityScores object from the MPMB source code."
    out = title_generator._fallback_title(msg)
    assert len(out) <= title_generator._FALLBACK_TRUNCATE + 1
    assert out.endswith("…")


def test_fallback_title_passes_through_short_message():
    assert title_generator._fallback_title("Hi") == "Hi"


def test_fallback_title_handles_empty():
    assert title_generator._fallback_title("   ") == "New Conversation"


def _patch_get_session(monkeypatch, title: str = "New Conversation"):
    async def fake_get(session_id):
        return SimpleNamespace(title=title)

    monkeypatch.setattr(title_generator.session_service, "get_session", fake_get)


@pytest.mark.asyncio
async def test_generate_session_title_uses_llm_response(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    async def fake_generate(**kwargs):
        captured["kwargs"] = kwargs
        return SimpleNamespace(content='"AbilityScores Object Lookup"')

    async def fake_update(session_id, **fields):
        captured["update"] = (session_id, fields)
        return None

    monkeypatch.setattr(title_generator, "agent_generate", fake_generate)
    monkeypatch.setattr(title_generator.session_service, "update_session", fake_update)
    _patch_get_session(monkeypatch)

    sid = uuid4()
    await title_generator.generate_session_title(sid, "Show me AbilityScores")

    assert captured["kwargs"]["user_prompt"] == "Show me AbilityScores"
    assert captured["update"][0] == sid
    assert captured["update"][1]["title"] == "AbilityScores Object Lookup"


@pytest.mark.asyncio
async def test_generate_session_title_uses_cheap_model(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    async def fake_generate(**kwargs):
        captured["kwargs"] = kwargs
        return SimpleNamespace(content="Spell List Lookup")

    async def fake_update(session_id, **fields):
        return None

    monkeypatch.setattr(title_generator, "agent_generate", fake_generate)
    monkeypatch.setattr(title_generator.session_service, "update_session", fake_update)
    _patch_get_session(monkeypatch)

    await title_generator.generate_session_title(uuid4(), "Show me AbilityScores")

    provider = title_generator.settings.default_llm_provider
    assert captured["kwargs"]["provider"] == provider
    assert captured["kwargs"]["model"] == title_generator.settings.cheap_model_for(provider)


@pytest.mark.asyncio
async def test_generate_session_title_skips_when_user_renamed(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {"updated": False}

    async def fake_generate(**kwargs):
        return SimpleNamespace(content="Auto Generated Title")

    async def fake_update(session_id, **fields):
        captured["updated"] = True
        return None

    monkeypatch.setattr(title_generator, "agent_generate", fake_generate)
    monkeypatch.setattr(title_generator.session_service, "update_session", fake_update)
    _patch_get_session(monkeypatch, title="My Custom Title")

    await title_generator.generate_session_title(uuid4(), "Show me AbilityScores")
    assert captured["updated"] is False


@pytest.mark.asyncio
async def test_generate_session_title_falls_back_on_llm_error(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    async def fake_generate(**kwargs):
        raise RuntimeError("api down")

    async def fake_update(session_id, **fields):
        captured["update"] = fields
        return None

    monkeypatch.setattr(title_generator, "agent_generate", fake_generate)
    monkeypatch.setattr(title_generator.session_service, "update_session", fake_update)
    _patch_get_session(monkeypatch)

    await title_generator.generate_session_title(uuid4(), "Find every place that calls processStats()")
    assert "processStats" in captured["update"]["title"]
