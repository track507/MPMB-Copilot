"""
Per-provider model catalogs for the settings UI

Anthropic and OpenAI model lists are fetched live from each provider's models endpoint, with a curated static fallback
when the fetch fails (no key, API down, network hiccup)

Each model carries its supported effort levels. Anthropic levels come from the live `capabilities.effort` tree when the
fetch succeeds, otherwise from a static table. OpenAI exposes no effort metadata on its endpoint, so its levels come from
pydantic-ai's per-model profile (`openai_supports_reasoning`) plus OpenAI's SDK `ReasoningEffort` scale. Ollama is empty.
The request path reads the cached levels synchronously via `effort_levels_for`

Results are cached briefly so the settings screen doesn't hit the provider on every load
Ollama is intentionally free-form (empty list) - local model names are arbitrary, so the frontend shows a plain input
"""

import asyncio
import time
from dataclasses import dataclass

from app.config import config
from app.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str
    # ? Empty tuple = effort is unsupported for this model (frontend hides the effort control)
    effort_levels: tuple[str, ...] = ()


# Static effort tables
# * Source of truth for the curated fallback and for any model the live capabilities lookup can't classify
# * Anthropic ordering is low -> max; OpenAI uses its own reasoning-effort scale
_ANTHROPIC_EFFORT: dict[str, tuple[str, ...]] = {
    "claude-opus-4-8": ("low", "medium", "high", "xhigh", "max"),
    "claude-opus-4-7": ("low", "medium", "high", "xhigh", "max"),
    "claude-opus-4-6": ("low", "medium", "high", "max"),
    "claude-sonnet-4-6": ("low", "medium", "high", "max"),
    "claude-fable-5": ("low", "medium", "high", "xhigh", "max"),
    # ! Haiku 4.5 and Sonnet 4.5 do not support effort
    "claude-haiku-4-5": (),
}

# ? Conservative fallback used only if the pydantic-ai profile / OpenAI SDK lookup fails
_OPENAI_EFFORT_FALLBACK: tuple[str, ...] = ("minimal", "low", "medium", "high")
_ANTHROPIC_EFFORT_ORDER: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")


def _openai_effort_levels(model_id: str) -> tuple[str, ...]:
    """
    Derive OpenAI reasoning-effort levels from pydantic-ai's per-model profile

    OpenAI's API exposes no effort metadata, but pydantic-ai's `openai_model_profile` knows
    per-model whether the model reasons, and the value scale is OpenAI's own SDK `ReasoningEffort` literal
    'none' is excluded - that is reasoning-off, not a depth tier

    Returns an empty tuple for non-reasoning models, the static scale if the lookup fails
    """
    try:
        import typing

        from openai.types.shared import ReasoningEffort
        from pydantic_ai.profiles.openai import openai_model_profile

        if not getattr(openai_model_profile(model_id), "openai_supports_reasoning", False):
            return ()
        # ? ReasoningEffort is Optional[Literal[...]]; unwrap to the literal's string members
        literal = next((arg for arg in typing.get_args(ReasoningEffort) if typing.get_args(arg)), ReasoningEffort)
        values = [v for v in typing.get_args(literal) if isinstance(v, str) and v != "none"]
        return tuple(values) or _OPENAI_EFFORT_FALLBACK
    except Exception as e:
        logger.warning(f"OpenAI effort profile lookup failed for {model_id}, using static scale: {e}")
        return _OPENAI_EFFORT_FALLBACK


# * Curated fallbacks
# ANTHROPIC_CURATED is used only when the live fetch fails
# OPENAI_CURATED doubles as the allowlist we filter the live OpenAI list against (its endpoint returns every model the key can see, including non-chat ones)
ANTHROPIC_CURATED: tuple[ModelOption, ...] = (
    ModelOption("claude-opus-4-8", "Claude Opus 4.8", _ANTHROPIC_EFFORT["claude-opus-4-8"]),
    ModelOption("claude-opus-4-7", "Claude Opus 4.7", _ANTHROPIC_EFFORT["claude-opus-4-7"]),
    ModelOption("claude-sonnet-4-6", "Claude Sonnet 4.6", _ANTHROPIC_EFFORT["claude-sonnet-4-6"]),
    ModelOption("claude-haiku-4-5", "Claude Haiku 4.5", _ANTHROPIC_EFFORT["claude-haiku-4-5"]),
    ModelOption("claude-fable-5", "Claude Fable 5", _ANTHROPIC_EFFORT["claude-fable-5"]),
)

OPENAI_CURATED: tuple[ModelOption, ...] = (
    ModelOption("gpt-5.5", "GPT-5.5", _openai_effort_levels("gpt-5.5")),
    ModelOption("gpt-5.4", "GPT-5.4", _openai_effort_levels("gpt-5.4")),
    ModelOption("gpt-5.4-mini", "GPT-5.4 mini", _openai_effort_levels("gpt-5.4-mini")),
    ModelOption("gpt-5.4-nano", "GPT-5.4 nano", _openai_effort_levels("gpt-5.4-nano")),
)

_CACHE_TTL_SEC = 3600.0
_cache: dict[str, tuple[float, list[ModelOption]]] = {}


def _anthropic_effort_from_capabilities(model_id: str, capabilities) -> tuple[str, ...]:
    """
    Derive supported effort levels from a live `ModelInfo.capabilities` object

    Falls back to the static table when the model exposes no effort capability
    """
    effort = getattr(capabilities, "effort", None) if capabilities is not None else None
    if effort is None or not getattr(effort, "supported", False):
        # ? No live effort info - trust the static table, defaulting to "unsupported" for unknown models
        return _ANTHROPIC_EFFORT.get(model_id, ())
    levels: list[str] = []
    for name in _ANTHROPIC_EFFORT_ORDER:
        support = getattr(effort, name, None)
        if support is not None and getattr(support, "supported", False):
            levels.append(name)
    return tuple(levels) or _ANTHROPIC_EFFORT.get(model_id, ())


async def _fetch_anthropic() -> list[ModelOption]:
    api_key = config.anthropic_api_key
    if not api_key:
        return list(ANTHROPIC_CURATED)
    try:
        from anthropic import AsyncAnthropic

        options: list[ModelOption] = []
        async with AsyncAnthropic(api_key=api_key) as client:
            async for model in client.models.list():
                label = getattr(model, "display_name", None) or model.id
                levels = _anthropic_effort_from_capabilities(model.id, getattr(model, "capabilities", None))
                options.append(ModelOption(model.id, label, levels))
        return options or list(ANTHROPIC_CURATED)
    except Exception as e:
        logger.warning(f"Anthropic model list fetch failed, using curated fallback: {e}")
        return list(ANTHROPIC_CURATED)


async def _fetch_openai() -> list[ModelOption]:
    api_key = config.openai_api_key
    if not api_key:
        return list(OPENAI_CURATED)
    try:
        from openai import AsyncOpenAI

        async with AsyncOpenAI(api_key=api_key) as client:
            page = await client.models.list()
            available = {m.id for m in page.data}
        # ? Use the live list only as an availability filter over curated entries
        # ? OpenAI's endpoint has no display names or effort metadata and lists many non-chat models
        filtered = [o for o in OPENAI_CURATED if o.id in available]
        return filtered or list(OPENAI_CURATED)
    except Exception as e:
        logger.warning(f"OpenAI model list fetch failed, using curated fallback: {e}")
        return list(OPENAI_CURATED)


async def _cached(provider: str, fetch) -> list[ModelOption]:
    now = time.time()
    hit = _cache.get(provider)
    if hit is not None and now - hit[0] < _CACHE_TTL_SEC:
        return hit[1]
    options = await fetch()
    _cache[provider] = (now, options)
    return options


def effort_levels_for(provider: str, model: str) -> tuple[str, ...]:
    """
    Return the effort levels for a model, read synchronously for the request path

    Prefers the warm catalog cache (so live Anthropic capabilities win), then the static tables
    Returns an empty tuple when effort is unsupported or the model is unknown
    """
    cached = _cache.get(provider)
    if cached is not None:
        for option in cached[1]:
            if option.id == model:
                return option.effort_levels
    if provider == "anthropic":
        return _ANTHROPIC_EFFORT.get(model, ())
    if provider == "openai":
        # ? Profile-driven: any reasoning-capable OpenAI model gets effort, unknown/non-reasoning get none
        return _openai_effort_levels(model)
    return ()


async def get_model_catalog() -> dict[str, list[dict]]:
    """
    Return selectable models per provider as `{provider: [{id, label, effort}]}`

    `effort` is the list of supported effort levels (empty = no effort control)
    Ollama is always empty (free-form input on the frontend)
    """
    anthropic, openai = await asyncio.gather(
        _cached("anthropic", _fetch_anthropic),
        _cached("openai", _fetch_openai),
    )
    return {
        "anthropic": [_serialize(o) for o in anthropic],
        "openai": [_serialize(o) for o in openai],
        "ollama": [],
    }


def _serialize(option: ModelOption) -> dict:
    return {"id": option.id, "label": option.label, "effort": list(option.effort_levels)}
