"""Tests for the hot-reloadable Settings (no disk I/O - fresh instances)."""

from app.settings import Settings


def test_cheap_model_for_anthropic_default():
    s = Settings(default_llm_provider="anthropic")
    assert s.cheap_model_for() == "claude-haiku-4-5-20251001"


def test_cheap_model_for_openai_default():
    s = Settings(default_llm_provider="openai")
    assert s.cheap_model_for() == "gpt-4o-mini"


def test_cheap_model_for_ollama_falls_back_to_default_model_when_blank():
    s = Settings(default_llm_provider="ollama", default_model="codellama", ollama_cheap_model="")
    assert s.cheap_model_for() == "codellama"


def test_cheap_model_for_explicit_provider_overrides_default():
    s = Settings(default_llm_provider="anthropic", openai_cheap_model="custom-mini")
    assert s.cheap_model_for(provider="openai") == "custom-mini"


def test_cheap_model_for_unknown_provider_uses_default_model():
    s = Settings(default_llm_provider="anthropic", default_model="some-model")
    assert s.cheap_model_for(provider="mystery") == "some-model"


def test_cheap_model_fields_serialized_in_to_dict():
    s = Settings()
    data = s.to_dict()
    assert "anthropic_cheap_model" in data
    assert "openai_cheap_model" in data
    assert "ollama_cheap_model" in data


def test_settings_update_schema_accepts_cheap_model_fields():
    from app.api.settings import SettingsUpdate

    body = SettingsUpdate(anthropic_cheap_model="claude-haiku-pinned")
    updates = body.model_dump(exclude_none=True)
    assert updates == {"anthropic_cheap_model": "claude-haiku-pinned"}
