"""Provider selection for PydanticAI agents.

Maps our provider + model + generation params into PydanticAI's
`(Model, ModelSettings)` pair. Anthropic gets cache-aware settings;
OpenAI and Ollama get plain `ModelSettings`.

This module owns the provider switch. Anything that wants an `Agent`
goes through `core.agent.build_agent`, which calls `build_model` here.
"""

from typing import Tuple

from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from app.config import config
from app.core.model_catalog import effort_levels_for
from app.settings import settings


def build_model(
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> Tuple[Model, ModelSettings]:
    """Build the PydanticAI `(Model, ModelSettings)` pair for a provider.

    Anthropic settings carry cache flags from `settings`. OpenAI and
    Ollama get a vanilla `ModelSettings`. Reasoning effort is applied only
    when the selected model advertises support for it (see `effort_levels_for`);
    pydantic-ai drops any sampling params the model rejects.
    """
    # ! Only pass effort the model actually supports, else omit (avoids a 400 on e.g. Haiku)
    effort = settings.default_effort if settings.default_effort in effort_levels_for(provider, model) else None

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
            anthropic_cache_tool_definitions=settings.anthropic_cache_tool_definitions,
        )
        if effort is not None:
            model_settings["anthropic_effort"] = effort
        if settings.enable_extended_thinking:
            # ? Adaptive thinking is the only form newer models accept; budget_tokens is rejected
            model_settings["anthropic_thinking"] = {"type": "adaptive"}
        return anthropic_model, model_settings

    if provider == "openai":
        api_key = config.openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set. Add it to .env or set the environment variable.")
        openai_model = OpenAIChatModel(
            model_name=model,
            provider=OpenAIProvider(api_key=api_key),
        )
        openai_settings = OpenAIChatModelSettings(temperature=temperature, max_tokens=max_tokens)
        if effort is not None:
            openai_settings["openai_reasoning_effort"] = effort
        return openai_model, openai_settings

    if provider == "ollama":
        ollama_model = OpenAIChatModel(
            model_name=model,
            provider=OllamaProvider(base_url=config.ollama_host),
        )
        return ollama_model, ModelSettings(temperature=temperature, max_tokens=max_tokens)

    raise ValueError(f"Unknown LLM provider: {provider}. Supported: anthropic, openai, ollama")
