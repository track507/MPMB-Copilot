"""Multi-provider LLM client using PydanticAI agents.

Wraps PydanticAI's `Agent` behind a unified interface with provider
switching (Anthropic, OpenAI, Ollama), streaming, token tracking, and
Anthropic prompt-cache support.

The client reads provider selection and behavioral params from
`settings` (hot-reloadable) and API keys / hosts from `config`
(infrastructure, restart-required).

Usage:
    from app.services.llm import llm_client

    # Non-streaming
    response = await llm_client.generate(messages)
    print(response.content)
    print(response.usage)

    # Streaming
    async for event in llm_client.stream(messages):
        print(event.content, end="", flush=True)

    # Override provider/model per call
    response = await llm_client.generate(
        messages, provider="openai", model="gpt-4o",
    )
"""

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from pydantic_ai import Agent
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

    # DEPRECATED: remove after parity tests. No consumers exist.
    raw: Optional[Any] = None


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


# * Message splitting
def _split_messages(messages: list[dict]) -> tuple[str, list[dict], str]:
    """Split a flat message list into (system_text, history, user_prompt).

    The legacy `build_messages()` returns a flat `list[dict]` with a
    system message first, conversation history in the middle, and the
    current user query last.  This function extracts those three parts
    so they can be routed to PydanticAI's `Agent(instructions=...)`,
    `message_history`, and `user_prompt` respectively.

    For the system content: if it's a list of Anthropic-style content
    blocks (dicts with `text` keys), the text parts are concatenated.
    PydanticAI handles cache_control via `AnthropicModelSettings`, so
    manual cache_control blocks are stripped.
    """
    system_text = ""
    history: list[dict] = []
    user_prompt = ""

    if not messages:
        return system_text, history, user_prompt

    start = 0
    # Extract system message (always first if present)
    if messages[0]["role"] == "system":
        raw_content = messages[0]["content"]
        if isinstance(raw_content, list):
            # Anthropic-style content blocks: [{"type": "text", "text": "...", ...}]
            system_text = "\n\n".join(
                block["text"] for block in raw_content if isinstance(block, dict) and "text" in block
            )
        else:
            system_text = str(raw_content)
        start = 1

    # Last message is the current user query
    if start < len(messages) and messages[-1]["role"] == "user":
        user_prompt = messages[-1]["content"]
        end = len(messages) - 1
    else:
        end = len(messages)

    # Everything in between is conversation history
    history = messages[start:end]

    return system_text, history, user_prompt


# * PydanticAI Agent factory
def _build_agent(
    instructions: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Agent:
    """Instantiate a PydanticAI `Agent` for the given provider.

    The static system instructions are passed as `instructions=` so they
    can be cached by Anthropic via `anthropic_cache_instructions`.  Per-turn
    RAG context belongs in the user prompt, not here, so the cache stays warm.

    Cache settings are applied only on the anthropic branch.  OpenAI and
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
        # Ollama exposes a Chat Completions-compatible API.
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


# * Client
class LLMClient:
    """Unified LLM client with streaming, caching, and provider switching."""

    async def generate(
        self,
        messages: list[dict],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a complete (non-streaming) response.

        Args:
            messages: Message dicts with 'role' and 'content' keys.
                System message (first item) becomes Agent instructions.
                Last user message becomes the prompt.
                Everything in between is conversation history.
            provider: Override the default provider.
            model: Override the default model.
            temperature: Override the default temperature.
            max_tokens: Override the default max tokens.

        Returns:
            LLMResponse with content, usage, and metadata.
        """
        resolved_provider = provider or settings.default_llm_provider
        resolved_model = model or settings.default_model

        system_text, history_dicts, user_prompt = _split_messages(messages)

        agent = _build_agent(
            instructions=system_text,
            provider=resolved_provider,
            model=resolved_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        pydantic_history = to_pydantic_messages(history_dicts)

        logger.info(
            f"LLM generate: provider={resolved_provider} model={resolved_model} "
            f"messages={len(messages)} history={len(pydantic_history)}"
        )

        result = await agent.run(user_prompt, message_history=pydantic_history)

        usage = _extract_usage(result.usage())

        return LLMResponse(
            content=result.output,
            provider=resolved_provider,
            model=resolved_model,
            usage=usage,
            stop_reason=None,  # PydanticAI doesn't expose stop_reason directly
            raw=None,
        )

    async def stream(
        self,
        messages: list[dict],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        """Stream a response as incremental events.

        Yields LLMStreamEvent objects.  The final event has
        `done=True` and includes usage metadata if available.
        """
        resolved_provider = provider or settings.default_llm_provider
        resolved_model = model or settings.default_model

        system_text, history_dicts, user_prompt = _split_messages(messages)

        agent = _build_agent(
            instructions=system_text,
            provider=resolved_provider,
            model=resolved_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        pydantic_history = to_pydantic_messages(history_dicts)

        logger.info(
            f"LLM stream: provider={resolved_provider} model={resolved_model} "
            f"messages={len(messages)} history={len(pydantic_history)}"
        )

        async with agent.run_stream(user_prompt, message_history=pydantic_history) as stream:
            async for delta in stream.stream_text(delta=True):
                yield LLMStreamEvent(content=delta)

            usage = _extract_usage(stream.usage())

        yield LLMStreamEvent(
            content="",
            done=True,
            usage=usage,
            stop_reason=None,
        )


# * Global instance
llm_client = LLMClient()
