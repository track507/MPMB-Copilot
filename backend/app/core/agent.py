"""Agent construction and invocation for the RAG pipeline.

Wraps PydanticAI's `Agent` with our provider switch (via
`services.llm.providers.build_model`), optional toolset attachment,
and unified response types.

Static system instructions are passed as `instructions=` so the
Anthropic instructions cache can apply. Per-turn RAG context belongs
in the user prompt, not here.
"""

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse
from pydantic_ai.toolsets import AbstractToolset

from app.logger import get_logger
from app.services.llm.messages import to_pydantic_messages
from app.services.llm.providers import build_model
from app.settings import settings

logger = get_logger(__name__)


# * Response types
@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""

    content: str
    provider: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    stop_reason: Optional[str] = None


@dataclass
class LLMStreamEvent:
    """Single event from a streaming LLM response."""

    content: str = ""
    done: bool = False
    usage: Optional[dict[str, Any]] = None
    stop_reason: Optional[str] = None


# * Factory
def build_agent(
    instructions: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    toolset: Optional[AbstractToolset[Any]] = None,
) -> Agent:
    """Construct an `Agent` for the given provider, optionally with a toolset.

    Tool attachment is controlled by the caller; `build_agent` stays
    agnostic about tool policy.
    """
    provider = provider or settings.default_llm_provider
    model = model or settings.default_model
    temperature = temperature if temperature is not None else settings.temperature
    max_tokens = max_tokens or settings.max_tokens

    pa_model, model_settings = build_model(
        provider=provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    kwargs: dict[str, Any] = {
        "instructions": instructions,
        "model_settings": model_settings,
    }
    if toolset is not None:
        kwargs["toolsets"] = [toolset]

    return Agent(pa_model, **kwargs)


# * Helpers
def _extract_usage(usage: Any) -> dict[str, Any]:
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cache_read_tokens": getattr(usage, "cache_read_tokens", 0) or 0,
        "cache_creation_tokens": getattr(usage, "cache_creation_tokens", 0) or 0,
    }


def _extract_stop_reason_from_messages(messages: list[Any]) -> Optional[str]:
    for message in reversed(messages):
        if not isinstance(message, ModelResponse):
            continue
        reason = getattr(message, "finish_reason", None)
        if reason is None:
            continue
        if hasattr(reason, "value"):
            return str(reason.value)
        return str(reason)
    return None


# * Invocation
async def generate(
    instructions: str,
    user_prompt: str,
    history: Optional[list[dict]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    toolset: Optional[AbstractToolset[Any]] = None,
    deps: Any = None,
    usage_limits: Any = None,
) -> LLMResponse:
    """Run a non-streaming agent call and return a `LLMResponse`."""
    resolved_provider = provider or settings.default_llm_provider
    resolved_model = model or settings.default_model

    agent = build_agent(
        instructions=instructions,
        provider=resolved_provider,
        model=resolved_model,
        temperature=temperature,
        max_tokens=max_tokens,
        toolset=toolset,
    )
    pydantic_history = to_pydantic_messages(history or [])

    logger.info(
        f"LLM generate: provider={resolved_provider} model={resolved_model} "
        f"history={len(pydantic_history)} tools={'yes' if toolset else 'no'}"
    )

    run_kwargs: dict[str, Any] = {"message_history": pydantic_history}
    if deps is not None:
        run_kwargs["deps"] = deps
    if usage_limits is not None:
        run_kwargs["usage_limits"] = usage_limits

    result = await agent.run(user_prompt, **run_kwargs)

    return LLMResponse(
        content=result.output,
        provider=resolved_provider,
        model=resolved_model,
        usage=_extract_usage(result.usage()),
        stop_reason=_extract_stop_reason_from_messages(result.new_messages()),
    )


async def stream(
    instructions: str,
    user_prompt: str,
    history: Optional[list[dict]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    toolset: Optional[AbstractToolset[Any]] = None,
    deps: Any = None,
    usage_limits: Any = None,
) -> AsyncIterator[LLMStreamEvent]:
    """Stream text deltas; final event carries usage + stop reason."""
    resolved_provider = provider or settings.default_llm_provider
    resolved_model = model or settings.default_model

    agent = build_agent(
        instructions=instructions,
        provider=resolved_provider,
        model=resolved_model,
        temperature=temperature,
        max_tokens=max_tokens,
        toolset=toolset,
    )
    pydantic_history = to_pydantic_messages(history or [])

    logger.info(
        f"LLM stream: provider={resolved_provider} model={resolved_model} "
        f"history={len(pydantic_history)} tools={'yes' if toolset else 'no'}"
    )

    run_kwargs: dict[str, Any] = {"message_history": pydantic_history}
    if deps is not None:
        run_kwargs["deps"] = deps
    if usage_limits is not None:
        run_kwargs["usage_limits"] = usage_limits

    async with agent.run_stream(user_prompt, **run_kwargs) as s:
        async for delta in s.stream_text(delta=True):
            yield LLMStreamEvent(content=delta)
        usage = _extract_usage(s.usage())
        stop_reason = _extract_stop_reason_from_messages(s.all_messages())

    yield LLMStreamEvent(content="", done=True, usage=usage, stop_reason=stop_reason)
