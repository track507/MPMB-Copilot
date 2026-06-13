"""
Live Anthropic prompt-caching smoke test

Skipped by default - run on demand with:
    RUN_LIVE_ANTHROPIC_TESTS=1 uv run pytest tests/services/llm/test_live_caching.py -v
Requires ANTHROPIC_API_KEY and spends a few thousand tokens.
"""

import os

import pytest


@pytest.mark.skipif(
    not os.getenv("RUN_LIVE_ANTHROPIC_TESTS"),
    reason="set RUN_LIVE_ANTHROPIC_TESTS=1 and ANTHROPIC_API_KEY to run",
)
@pytest.mark.asyncio
async def test_live_anthropic_caching_writes_then_reads():
    from app.core.agent import generate

    # Instructions must exceed the ~1024-token cacheable minimum for Sonnet
    instructions = "You are a concise test assistant for verifying prompt caching. " * 150

    first = await generate(instructions=instructions, user_prompt="Say hello.", provider="anthropic")
    assert first.usage["cache_write_tokens"] > 0, f"expected cache write on turn 1, got {first.usage}"

    history = [
        {"role": "user", "content": "Say hello."},
        {"role": "assistant", "content": first.content},
    ]
    second = await generate(
        instructions=instructions,
        user_prompt="Say hello again.",
        history=history,
        provider="anthropic",
    )
    assert second.usage["cache_read_tokens"] > 0, f"expected cache read on turn 2, got {second.usage}"
