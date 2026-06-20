"""Settings API endpoint.

Exposes the hot-reloadable behavioral settings from `app.settings` for
the frontend settings panel. GET returns the current state, PATCH
applies a partial update and persists to disk.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import Principal, require_admin
from app.logger import get_logger
from app.settings import settings

logger = get_logger(__name__)
router = APIRouter()


class SettingsUpdate(BaseModel):
    """Partial settings update. All fields optional."""

    default_llm_provider: str | None = None
    default_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    default_effort: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    anthropic_cheap_model: str | None = None
    openai_cheap_model: str | None = None
    ollama_cheap_model: str | None = None
    default_edition: str | None = None
    top_k_results: int | None = None
    similarity_threshold: float | None = None
    context_window_size: int | None = None
    retrieval_mode: str | None = None
    intent_method: str | None = None
    intent_confidence_threshold: float | None = None
    intent_confidence_margin: float | None = None
    tier_budgets: dict[str, dict[str, int]] | None = None
    rerank_enabled: bool | None = None
    rerank_provider: str | None = None
    rerank_model: str | None = None
    rerank_candidate_k: int | None = None
    enable_tool_use: bool | None = None
    max_tool_calls: int | None = None
    tool_search_limit: int | None = None
    anthropic_cache_instructions: bool | None = None
    anthropic_cache_messages: bool | None = None
    enable_extended_thinking: bool | None = None
    system_prompt: str | None = None
    source_catalog_path: Optional[str] = None
    source_catalog_enabled: Optional[bool] = None
    inject_catalog_context: Optional[bool] = None


@router.get(
    "/settings",
    status_code=status.HTTP_200_OK,
    summary="Get current behavioral settings",
)
async def get_settings() -> dict[str, Any]:
    """Return the current hot-reloadable settings as a dict."""
    return settings.to_dict()


@router.get(
    "/models",
    status_code=status.HTTP_200_OK,
    summary="List selectable models per provider",
)
async def get_models() -> dict[str, list[dict[str, Any]]]:
    """
    Return `{provider: [{id, label, effort}]}` for the settings model pickers

    `effort` is the list of supported effort levels (empty = no effort control)
    Anthropic/OpenAI are fetched live with a curated fallback
    Ollama is empty (free-form)

    Never raises - falls back to curated lists on any failure
    """
    from app.core.model_catalog import get_model_catalog

    return await get_model_catalog()


@router.get(
    "/embedding-models",
    status_code=status.HTTP_200_OK,
    summary="List selectable embedding models with availability",
)
async def get_embedding_models() -> dict[str, Any]:
    """
    Return `{models: [...], current: {provider, model}}` for the embedding picker

    Each model carries its fixed dimension, multilingual flag, pinned flag, and a status of ready/needs_key/installable
    Never raise
    """
    from app.core.embedding_catalog import serialize

    return {
        "models": serialize(),
        "current": {"provider": settings.embedding_provider, "model": settings.embedding_model},
    }


@router.get(
    "/capabilities",
    status_code=status.HTTP_200_OK,
    summary="List all selectable capabilities for the store",
)
async def get_capabilities(_: Principal = Depends(require_admin)) -> dict[str, Any]:
    """
    Unified provider/capability catalog for the settings store

    Returns `{capability: {label, kind, entries, current}}` for generation, embedding, rerank, and vector store
    Admin-gated (store/provider config is admin-only); the gate is a no-op single-admin today
    """
    from app.core.registry import serialize_all

    return await serialize_all()


@router.patch(
    "/settings",
    status_code=status.HTTP_200_OK,
    summary="Update behavioral settings",
    description="Partial update. Only fields present in the body are changed.",
)
async def update_settings(body: SettingsUpdate, _: Principal = Depends(require_admin)) -> dict[str, Any]:
    """Apply a partial settings update and persist to disk."""
    updates = body.model_dump(exclude_none=True)

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    try:
        settings.update(**updates)
    except Exception as e:
        logger.error(f"Failed to update settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update settings: {str(e)}",
        )

    return settings.to_dict()
