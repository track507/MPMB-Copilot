import pytest
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import config
from app.services.llm.providers import build_model


def test_build_model_anthropic(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "anthropic_api_key", "test-key")
    model, model_settings = build_model(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        temperature=0.4,
        max_tokens=1234,
    )
    assert isinstance(model, AnthropicModel)
    assert isinstance(model.provider, AnthropicProvider)
    assert isinstance(model_settings, dict)
    assert model_settings["temperature"] == 0.4
    assert model_settings["max_tokens"] == 1234
    assert "anthropic_cache_instructions" in model_settings
    assert "anthropic_cache_messages" in model_settings
    assert "anthropic_cache_tool_definitions" in model_settings


def test_build_model_openai(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "openai_api_key", "test-key")
    model, model_settings = build_model(
        provider="openai",
        model="gpt-4o",
        temperature=0.1,
        max_tokens=222,
    )
    assert isinstance(model, OpenAIChatModel)
    assert isinstance(model.provider, OpenAIProvider)
    assert isinstance(model_settings, dict)
    assert model_settings["temperature"] == 0.1
    assert model_settings["max_tokens"] == 222


def test_build_model_ollama():
    model, model_settings = build_model(
        provider="ollama",
        model="llama3",
        temperature=0.7,
        max_tokens=333,
    )
    assert isinstance(model, OpenAIChatModel)
    assert isinstance(model.provider, OllamaProvider)
    assert model_settings["temperature"] == 0.7
    assert model_settings["max_tokens"] == 333


def test_build_model_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        build_model(provider="nope", model="x", temperature=0.1, max_tokens=10)


def test_build_model_anthropic_missing_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "anthropic_api_key", None)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        build_model(provider="anthropic", model="x", temperature=0.1, max_tokens=10)
