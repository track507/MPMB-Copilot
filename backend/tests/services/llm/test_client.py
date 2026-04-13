from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import config
from app.services.llm.client import (
    LLMStreamEvent,
    _build_agent,
    _extract_stop_reason_from_messages,
    llm_client,
)


def test_build_agent_selects_anthropic_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "anthropic_api_key", "test-key")

    agent = _build_agent(
        instructions="Static instructions",
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        temperature=0.4,
        max_tokens=1234,
    )

    assert isinstance(agent.model, AnthropicModel)
    assert isinstance(agent.model.provider, AnthropicProvider)
    assert agent.model_settings["temperature"] == 0.4
    assert agent.model_settings["max_tokens"] == 1234
    assert "anthropic_cache_instructions" in agent.model_settings
    assert "anthropic_cache_messages" in agent.model_settings


def test_build_agent_selects_openai_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "openai_api_key", "test-key")

    agent = _build_agent(
        instructions="Static instructions",
        provider="openai",
        model="gpt-4o",
        temperature=0.1,
        max_tokens=222,
    )

    assert isinstance(agent.model, OpenAIChatModel)
    assert isinstance(agent.model.provider, OpenAIProvider)
    assert agent.model_settings == {"temperature": 0.1, "max_tokens": 222}


def test_build_agent_selects_ollama_provider():
    agent = _build_agent(
        instructions="Static instructions",
        provider="ollama",
        model="llama3",
        temperature=0.7,
        max_tokens=333,
    )

    assert isinstance(agent.model, OpenAIChatModel)
    assert isinstance(agent.model.provider, OllamaProvider)
    assert agent.model_settings == {"temperature": 0.7, "max_tokens": 333}


def test_extract_stop_reason_returns_none_without_response_reason():
    assert _extract_stop_reason_from_messages([]) is None


def test_extract_stop_reason_uses_last_model_response():
    messages: list[Any] = [
        ModelResponse(parts=[TextPart(content="partial")], model_name="test", finish_reason="length"),
        ModelResponse(parts=[TextPart(content="final")], model_name="test", finish_reason="stop"),
    ]

    assert _extract_stop_reason_from_messages(messages) == "stop"


@pytest.mark.asyncio
async def test_generate_returns_expected_shape(monkeypatch: pytest.MonkeyPatch):
    def fake_build_agent(*args: Any, **kwargs: Any) -> Agent:
        return Agent(TestModel(custom_output_text="hello from test model"), instructions="Static instructions")

    monkeypatch.setattr("app.services.llm.client._build_agent", fake_build_agent)

    response = await llm_client.generate(
        instructions="Static instructions",
        user_prompt="RAG context\n\n---\n\nUser question: hi",
        history=[{"role": "assistant", "content": "Earlier answer"}],
        provider="anthropic",
        model="claude-sonnet-4-20250514",
    )

    assert response.content == "hello from test model"
    assert response.provider == "anthropic"
    assert response.model == "claude-sonnet-4-20250514"
    assert response.stop_reason is None
    assert response.usage["input_tokens"] >= 0
    assert response.usage["output_tokens"] >= 0
    assert response.usage["total_tokens"] == response.usage["input_tokens"] + response.usage["output_tokens"]


@pytest.mark.asyncio
async def test_stream_returns_text_then_final_event(monkeypatch: pytest.MonkeyPatch):
    def fake_build_agent(*args: Any, **kwargs: Any) -> Agent:
        return Agent(TestModel(custom_output_text="streamed hello"), instructions="Static instructions")

    monkeypatch.setattr("app.services.llm.client._build_agent", fake_build_agent)

    events = [
        event
        async for event in llm_client.stream(
            instructions="Static instructions",
            user_prompt="RAG context\n\n---\n\nUser question: hi",
            history=[{"role": "assistant", "content": "Earlier answer"}],
            provider="openai",
            model="gpt-4o",
        )
    ]

    assert events
    assert any(event.content for event in events[:-1])

    final_event = events[-1]
    assert isinstance(final_event, LLMStreamEvent)
    assert final_event.done is True
    assert final_event.content == ""
    assert final_event.stop_reason is None
    assert final_event.usage is not None
    assert final_event.usage["total_tokens"] == final_event.usage["input_tokens"] + final_event.usage["output_tokens"]
