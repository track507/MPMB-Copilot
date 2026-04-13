"""Settings API endpoint.

Exposes the hot-reloadable behavioral settings from `app.settings` for
the frontend settings panel. GET returns the current state, PATCH
applies a partial update and persists to disk.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

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
    default_edition: str | None = None
    top_k_results: int | None = None
    similarity_threshold: float | None = None
    context_window_size: int | None = None
    retrieval_mode: str | None = None
    intent_method: str | None = None
    intent_confidence_threshold: float | None = None
    intent_confidence_margin: float | None = None
    tier_budgets: dict[str, dict[str, int]] | None = None
    enable_tool_use: bool | None = None
    max_tool_calls: int | None = None
    tool_search_limit: int | None = None
    anthropic_cache_instructions: bool | None = None
    anthropic_cache_messages: bool | None = None
    enable_extended_thinking: bool | None = None
    thinking_budget_tokens: int | None = None
    system_prompt: str | None = None


@router.get(
    "/settings",
    status_code=status.HTTP_200_OK,
    summary="Get current behavioral settings",
)
async def get_settings() -> dict[str, Any]:
    """Return the current hot-reloadable settings as a dict."""
    return settings.to_dict()


@router.patch(
    "/settings",
    status_code=status.HTTP_200_OK,
    summary="Update behavioral settings",
    description="Partial update. Only fields present in the body are changed.",
)
async def update_settings(body: SettingsUpdate) -> dict[str, Any]:
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
