"""Multi-provider LLM client using LangChain chat models.

Wraps `langchain-anthropic`, `langchain-openai`, and
`langchain-ollama` behind a unified interface.  This saves ~300 lines
of provider-specific SDK code and gives us streaming, token tracking,
and prompt caching with minimal maintenance.

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

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages import HumanMessage as LCHumanMessage
from langchain_core.messages import SystemMessage as LCSystemMessage

from app.config import config
from app.logger import get_logger
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

    raw: Optional[Any] = None
    """Raw LangChain AIMessage for advanced inspection."""


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


# * Message conversion
def _to_langchain_messages(messages: list[dict]) -> list[BaseMessage]:
    """Convert raw message dicts to LangChain message objects.

    Handles Anthropic-style system content blocks (list of dicts with
    cache_control) and plain string content for other providers.
    """
    lc_messages: list[BaseMessage] = []

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "system":
            # LangChain SystemMessage accepts either str or list of content blocks
            lc_messages.append(LCSystemMessage(content=content))
        elif role == "user":
            lc_messages.append(LCHumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        else:
            logger.warning(f"Unknown message role: {role}, treating as user")
            lc_messages.append(LCHumanMessage(content=content))

    return lc_messages


# * Provider factory
def _build_chat_model(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
):
    """Instantiate the appropriate LangChain chat model.

    Reads from settings (hot-reloadable) for defaults, config for
    infrastructure (API keys, hosts).
    """
    provider = provider or settings.default_llm_provider
    model = model or settings.default_model
    temperature = temperature if temperature is not None else settings.temperature
    max_tokens = max_tokens or settings.max_tokens

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        api_key = config.anthropic_api_key
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set. Add it to .env or set the environment variable.")

        return ChatAnthropic(
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    elif provider == "openai":
        from langchain_openai import ChatOpenAI

        api_key = config.openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set. Add it to .env or set the environment variable.")

        return ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    elif provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            raise ImportError("langchain-ollama is not installed. Install it with: pip install langchain-ollama")

        return ChatOllama(
            model=model,
            base_url=config.ollama_host,
            temperature=temperature,
            num_predict=max_tokens,
        )

    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Supported: anthropic, openai, ollama")


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
                                                System messages may have content blocks with
                                                cache_control for Anthropic.
            provider: Override the default provider.
            model: Override the default model.
            temperature: Override the default temperature.
            max_tokens: Override the default max tokens.

        Returns:
            LLMResponse with content, usage, and metadata.
        """
        resolved_provider = provider or settings.default_llm_provider
        resolved_model = model or settings.default_model

        chat_model = _build_chat_model(
            provider=resolved_provider,
            model=resolved_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        lc_messages = _to_langchain_messages(messages)

        logger.info(f"LLM generate: provider={resolved_provider} model={resolved_model} messages={len(messages)}")

        response: AIMessage = await chat_model.ainvoke(lc_messages)

        usage = self._extract_usage(response, resolved_provider)

        return LLMResponse(
            content=response.content,
            provider=resolved_provider,
            model=resolved_model,
            usage=usage,
            stop_reason=response.response_metadata.get("stop_reason"),
            raw=response,
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

        chat_model = _build_chat_model(
            provider=resolved_provider,
            model=resolved_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        lc_messages = _to_langchain_messages(messages)

        logger.info(f"LLM stream: provider={resolved_provider} model={resolved_model} messages={len(messages)}")

        full_response: Optional[AIMessageChunk] = None

        async for chunk in chat_model.astream(lc_messages):
            # Accumulate for final usage extraction
            if full_response is None:
                full_response = chunk
            else:
                full_response = full_response + chunk

            yield LLMStreamEvent(
                content=chunk.content if isinstance(chunk.content, str) else "",
            )

        # Final event with usage
        usage = {}
        if full_response:
            usage = self._extract_usage(full_response, resolved_provider)

        yield LLMStreamEvent(
            content="",
            done=True,
            usage=usage,
            stop_reason=(full_response.response_metadata.get("stop_reason") if full_response else None),
        )

    def _extract_usage(self, response, provider: str) -> dict[str, Any]:
        """Extract token usage from a LangChain response.

        Handles different metadata structures across providers.
        """
        usage: dict[str, Any] = {}

        # LangChain standardized usage_metadata
        meta = getattr(response, "usage_metadata", None)
        if meta:
            usage["input_tokens"] = meta.get("input_tokens", 0)
            usage["output_tokens"] = meta.get("output_tokens", 0)
            usage["total_tokens"] = meta.get("total_tokens", 0)

            # Anthropic cache details
            input_details = meta.get("input_token_details", {})
            if input_details:
                usage["cache_read_tokens"] = input_details.get("cache_read", 0)
                usage["cache_creation_tokens"] = input_details.get("cache_creation", 0)

        return usage


# * Global instance
llm_client = LLMClient()
