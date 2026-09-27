from typing import Any, cast

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.test import TestModel

from app.config import config
from app.core.agent import (
    LLMStreamEvent,
    _extract_stop_reason_from_messages,
    build_agent,
    generate,
    stream,
)


def test_build_agent_returns_agent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "anthropic_api_key", "test-key")
    from app.services.llm.providers import build_model

    agent = build_agent(
        model_factory=build_model,
        instructions="Static instructions",
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        temperature=0.3,
        max_tokens=500,
    )
    assert isinstance(agent, Agent)


def test_extract_stop_reason_returns_none_without_responses():
    assert _extract_stop_reason_from_messages([]) is None


def test_extract_stop_reason_uses_last_model_response():
    messages: list[Any] = [
        ModelResponse(parts=[TextPart(content="partial")], model_name="test", finish_reason="length"),
        ModelResponse(parts=[TextPart(content="final")], model_name="test", finish_reason="stop"),
    ]
    assert _extract_stop_reason_from_messages(messages) == "stop"


@pytest.mark.asyncio
async def test_generate_returns_shape(monkeypatch: pytest.MonkeyPatch):
    def fake_build_agent(*args: Any, **kwargs: Any) -> Agent:
        return Agent(TestModel(custom_output_text="hello from test model"), instructions="Static")

    monkeypatch.setattr("app.core.agent.build_agent", fake_build_agent)

    response = await generate(
        model_factory=cast(Any, None),
        instructions="Static",
        user_prompt="RAG\n\n---\n\nUser question: hi",
        history=[{"role": "assistant", "content": "earlier"}],
        provider="anthropic",
        model="claude-sonnet-4-20250514",
    )
    assert response.content == "hello from test model"
    assert response.provider == "anthropic"
    assert response.model == "claude-sonnet-4-20250514"
    assert response.usage["total_tokens"] == response.usage["input_tokens"] + response.usage["output_tokens"]


@pytest.mark.asyncio
async def test_stream_returns_text_then_final_event(monkeypatch: pytest.MonkeyPatch):
    def fake_build_agent(*args: Any, **kwargs: Any) -> Agent:
        return Agent(TestModel(custom_output_text="streamed hello"), instructions="Static")

    monkeypatch.setattr("app.core.agent.build_agent", fake_build_agent)

    events = [
        e
        async for e in stream(
            model_factory=cast(Any, None),
            instructions="Static",
            user_prompt="RAG\n\n---\n\nUser question: hi",
            history=[],
            provider="openai",
            model="gpt-4o",
        )
    ]
    assert events
    assert any(e.content for e in events[:-1])
    final = events[-1]
    assert isinstance(final, LLMStreamEvent)
    assert final.done is True
    assert final.usage is not None


def test_extract_usage_maps_cache_write_tokens():
    from app.core.agent import _extract_usage

    class FakeUsage:
        input_tokens = 100
        output_tokens = 50
        cache_read_tokens = 70
        cache_write_tokens = 30

    usage = _extract_usage(FakeUsage())
    assert usage["input_tokens"] == 100
    assert usage["total_tokens"] == 150
    assert usage["cache_read_tokens"] == 70
    assert usage["cache_write_tokens"] == 30


def test_usage_carries_cost_as_a_string():
    """
    ! A float would lose precision below a cent, and these values get summed across a session

    genai-prices returns a Decimal, which json cannot serialize, so the string is both the safe and the only option
    """
    from decimal import Decimal

    from app.core.agent import _extract_usage

    class FakeUsage:
        input_tokens = 1000
        output_tokens = 200
        cost = Decimal("0.0043")

    usage = _extract_usage(FakeUsage())
    assert usage["cost_usd"] == "0.0043"
    assert isinstance(usage["cost_usd"], str)


def test_an_unpriced_model_reports_cost_as_none_not_zero():
    """
    ? genai-prices has no entry for every model, and zero would read as free

    Three states, never two: a number, unknown, or no limit set
    """
    from app.core.agent import _extract_usage

    class FakeUsage:
        input_tokens = 1000
        output_tokens = 200
        cost = None

    assert _extract_usage(FakeUsage())["cost_usd"] is None


def test_usage_from_an_object_with_no_cost_attribute_does_not_raise():
    """! Every provider's usage object reaches this function, and not all of them carry a cost field"""
    from app.core.agent import _extract_usage

    class BareUsage:
        input_tokens = 10
        output_tokens = 5

    assert _extract_usage(BareUsage())["cost_usd"] is None
