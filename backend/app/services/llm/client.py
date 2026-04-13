"""Multi-provider LLM client using PydanticAI agents.

Wraps PydanticAI's `Agent` behind a unified interface with provider
switching (Anthropic, OpenAI, Ollama), streaming, token tracking, and
Anthropic prompt-cache support.

The client reads provider selection and behavioral params from
`settings` (hot-reloadable) and API keys / hosts from `config`
(infrastructure, restart-required).

Usage:
    from app.services.llm import llm_client

    response = await llm_client.generate(
        instructions="You are a helpful assistant.",
        user_prompt="Hello",
    )

    async for event in llm_client.stream(
        instructions="...",
        user_prompt="Hello",
        history=[{"role": "user", "content": "earlier turn"}],
    ):
        print(event.content, end="", flush=True)
"""

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from app.config import config
from app.logger import get_logger
from app.services.llm.messages import to_pydantic_messages
from app.settings import settings

logger = get_logger(__name__)


# * Response types
@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""

    content: str
    """Generated text."""

    provider: str
    """Provider that handled the request."""

    model: str
    """Model that generated the response."""

    usage: dict[str, Any] = field(default_factory=dict)
    """Token usage: input_tokens, output_tokens, total_tokens, cache details."""

    stop_reason: Optional[str] = None
    """Why generation stopped (end_turn, max_tokens, etc.)."""


@dataclass
class LLMStreamEvent:
    """Single event from a streaming LLM response."""

    content: str = ""
    """Incremental text chunk."""

    done: bool = False
    """True when the stream is complete."""

    usage: Optional[dict[str, Any]] = None
    """Token usage - populated only on the final event."""

    stop_reason: Optional[str] = None
    """Stop reason - populated only on the final event."""


# * PydanticAI Agent factory
def _build_agent(
    instructions: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Agent:
    """Instantiate a PydanticAI `Agent` for the given provider.

    Static system instructions are passed as `instructions=` so they can
    be cached by Anthropic via `anthropic_cache_instructions`. Per-turn
    RAG context belongs in the user prompt, not here, so the cache stays
    warm.

    Cache settings are applied only on the anthropic branch. OpenAI and
    Ollama get plain `ModelSettings`.
    """
    provider = provider or settings.default_llm_provider
    model = model or settings.default_model
    temperature = temperature if temperature is not None else settings.temperature
    max_tokens = max_tokens or settings.max_tokens

    if provider == "anthropic":
        api_key = config.anthropic_api_key
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set. Add it to .env or set the environment variable.")

        anthropic_model = AnthropicModel(
            model_name=model,
            provider=AnthropicProvider(api_key=api_key),
        )
        model_settings = AnthropicModelSettings(
            temperature=temperature,
            max_tokens=max_tokens,
            anthropic_cache_instructions=settings.anthropic_cache_instructions,
            anthropic_cache_messages=settings.anthropic_cache_messages,
        )
        return Agent(anthropic_model, instructions=instructions, model_settings=model_settings)

    elif provider == "openai":
        api_key = config.openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set. Add it to .env or set the environment variable.")

        openai_model = OpenAIChatModel(
            model_name=model,
            provider=OpenAIProvider(api_key=api_key),
        )
        model_settings = ModelSettings(
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return Agent(openai_model, instructions=instructions, model_settings=model_settings)

    elif provider == "ollama":
        ollama_model = OpenAIChatModel(
            model_name=model,
            provider=OllamaProvider(base_url=config.ollama_host),
        )
        model_settings = ModelSettings(
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return Agent(ollama_model, instructions=instructions, model_settings=model_settings)

    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Supported: anthropic, openai, ollama")


# * Usage extraction
def _extract_usage(usage) -> dict[str, Any]:
    """Map PydanticAI `Usage` to our standard dict shape.

    PydanticAI's `Usage` has no `total_tokens`; we compute it.
    Cache fields may be zero for non-Anthropic providers.
    """
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
    """Best-effort extraction of a stop reason from model response messages.

    PydanticAI does not expose a provider-agnostic stop reason on the top-level
    result object. The most reliable cross-provider signal we have is the final
    `ModelResponse.finish_reason` when present.
    """
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


# * Client
class LLMClient:
    """Unified LLM client with streaming, caching, and provider switching."""

    async def generate(
        self,
        instructions: str,
        user_prompt: str,
        history: Optional[list[dict]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a complete (non-streaming) response.

        Args:
            instructions: Static system prompt for `Agent(instructions=...)`.
            user_prompt: Current user message (may include per-turn RAG context).
            history: Prior conversation messages as dicts with `role` and
                `content` keys (from the session DB).
            provider: Override the default provider.
            model: Override the default model.
            temperature: Override the default temperature.
            max_tokens: Override the default max tokens.

        Returns:
            LLMResponse with content, usage, and metadata.
        """
        resolved_provider = provider or settings.default_llm_provider
        resolved_model = model or settings.default_model

        agent = _build_agent(
            instructions=instructions,
            provider=resolved_provider,
            model=resolved_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        pydantic_history = to_pydantic_messages(history or [])

        logger.info(
            f"LLM generate: provider={resolved_provider} model={resolved_model} history={len(pydantic_history)}"
        )

        result = await agent.run(user_prompt, message_history=pydantic_history)

        usage = _extract_usage(result.usage())
        stop_reason = _extract_stop_reason_from_messages(result.new_messages())

        return LLMResponse(
            content=result.output,
            provider=resolved_provider,
            model=resolved_model,
            usage=usage,
            stop_reason=stop_reason,
        )

    async def stream(
        self,
        instructions: str,
        user_prompt: str,
        history: Optional[list[dict]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        """Stream a response as incremental events.

        Yields `LLMStreamEvent` objects. The final event has `done=True`
        and includes usage metadata if available.
        """
        resolved_provider = provider or settings.default_llm_provider
        resolved_model = model or settings.default_model

        agent = _build_agent(
            instructions=instructions,
            provider=resolved_provider,
            model=resolved_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        pydantic_history = to_pydantic_messages(history or [])

        logger.info(f"LLM stream: provider={resolved_provider} model={resolved_model} history={len(pydantic_history)}")

        async with agent.run_stream(user_prompt, message_history=pydantic_history) as stream:
            async for delta in stream.stream_text(delta=True):
                yield LLMStreamEvent(content=delta)

            usage = _extract_usage(stream.usage())
            stop_reason = _extract_stop_reason_from_messages(stream.all_messages())

        yield LLMStreamEvent(
            content="",
            done=True,
            usage=usage,
            stop_reason=stop_reason,
        )


# * Global instance
llm_client = LLMClient()
