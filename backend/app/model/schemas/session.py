"""Pydantic models for session API endpoints."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    """Request body for creating a session."""

    title: str = Field("New Conversation", min_length=1, max_length=255)
    edition: Optional[str] = Field(None, description="Default D&D edition (2014/2024)")
    settings: Optional[dict[str, Any]] = Field(None, description="Session-specific settings")


class SessionUpdate(BaseModel):
    """Request body for updating a session."""

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    settings: Optional[dict[str, Any]] = None
    meta_data: Optional[dict[str, Any]] = None


class MessageOut(BaseModel):
    """Message in API responses."""

    id: UUID
    session_id: UUID
    role: str
    content: dict[str, Any]
    created_at: datetime
    sequence_number: int
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: Optional[int] = None
    stop_reason: Optional[str] = None
    meta_data: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    """Session in API responses."""

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    user_id: Optional[str] = None
    settings: dict[str, Any] = Field(default_factory=dict)
    meta_data: dict[str, Any] = Field(default_factory=dict)
    message_count: int = 0

    model_config = {"from_attributes": True}


class SessionDetailOut(SessionOut):
    """Session with messages included."""

    messages: list[MessageOut] = Field(default_factory=list)


class SessionListOut(BaseModel):
    """Paginated session list response."""

    sessions: list[SessionOut]
    total: int
    limit: int
    offset: int
