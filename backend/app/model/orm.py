"""Database models (SQLAlchemy ORM)

This module defines the core database schema for MPMB-Copilot using SQLAlchemy ORM.
Uses UUID7 for all primary keys to provide time-ordered identifiers with better
index performance than random UUID4.

Models:
    Session: Conversation/chat session
    Message: Individual messages within sessions
    File: Uploaded files attached to sessions
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from uuid_utils import uuid7


class Base(DeclarativeBase):
    """
    Base class for all database models
    """

    pass


class Session(Base):
    """
    Conversation session model

    Represents a single chat conversation containing multiple messages and files
    Sessions use soft deletion (deleted_at) to preserve conversation history

    The UUID7 primary key ensures sessions are naturally ordered by creation time, improving query performance when fetching recent conversations

    Attributes:
        id: UUID7 primary key (time-ordered)
        title: Human-readable session title, defaults to "New Conversation"
        created_at: Timestamp when session was created (UTC)
        updated_at: Timestamp of last activity (UTC, auto-updated)
        user_id: Optional user identifier for multi-user support
        settings: Session-specific settings as JSONB. Structure:
            {
                "provider": "anthropic",  # Default LLM provider
                "model": "claude-sonnet-4-5",  # Default model
                "temperature": 0.2,  # Default temperature
                "max_tokens": 4000,  # Default max tokens
                "include_sources": true  # Whether to include RAG sources
            }
        meta_data: Additional session metadata as JSONB. Structure:
            {
                "tags": ["mpmb", "spells"],  # User-defined tags
                "pinned": false,  # Whether session is pinned
                "total_messages": 42,  # Message count (denormalized)
                "total_tokens": 15000  # Total token usage
            }
        deleted_at: Soft deletion timestamp (NULL if active)

    Relationships:
        messages: One-to-many with Message (cascade delete)
        files: One-to-many with File (cascade delete)

    Note:
        Uses cascade="all, delete-orphan" to ensure when a session is deleted, all associated messages and files are automatically removed from the database
    """

    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New Conversation")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    messages: Mapped[list["Message"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    files: Mapped[list["File"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)


class Message(Base):
    """
    Individual message within a conversation session

    Stores message content, role (user/assistant/system), and comprehensive LLM usage metrics for cost tracking and performance monitoring

    Messages are ordered within a session using sequence_number to ensure consistent conversation flow even if created_at timestamps are identical

    Attributes:
        id: UUID7 primary key (time-ordered)
        session_id: Foreign key to parent Session
        role: Message role - 'user', 'assistant', or 'system'
        content: Message content as JSONB. Structure varies by role:
            User message: {"text": "How do I add a spell?"}
            Assistant message: {
                "text": "To add a spell...",
                "sources": [{"file": "spells.js", "score": 0.89, ...}]
            }
            System message: {"text": "You are a helpful MPMB assistant..."}
        created_at: Timestamp when message was created (UTC)

        LLM Tracking Fields:
        provider: LLM provider used (e.g., "anthropic", "openai", "ollama")
        model: Specific model used (e.g., "claude-sonnet-4-5")
        prompt_tokens: Number of tokens in the prompt/input
        completion_tokens: Number of tokens in the completion/output
        total_tokens: Sum of prompt_tokens + completion_tokens
        latency_ms: Time taken to generate response in milliseconds
        stop_reason: Why generation stopped (e.g., "end_turn", "max_tokens")

        meta_data: Additional message metadata as JSONB. Structure:
            {
                "retrieval_time_ms": 45,  # Time spent retrieving context
                "chunks_retrieved": 5,  # Number of RAG chunks used
                "context_window_used": 0.65,  # Percentage of context used
                "truncated": false  # Whether response was truncated
            }
        sequence_number: Message order within session (1, 2, 3, ...)

    Relationships:
        session: Many-to-one with Session

    Note:
        CASCADE deletion ensures messages are removed when parent session is deleted
    """

    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # LLM tracking
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stop_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    meta_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    session: Mapped["Session"] = relationship(back_populates="messages")
    feedback: Mapped[Optional["MessageFeedback"]] = relationship(
        back_populates="message",
        uselist=False,
        cascade="all, delete-orphan",
    )


class File(Base):
    """
    Uploaded file attachment model

    Tracks files uploaded during conversations, storing both the original filename and the sanitized filesystem path
    Files can be attached to entire sessions or specific messages

    Attributes:
        id: UUID7 primary key (time-ordered)
        session_id: Foreign key to parent Session
        message_id: Optional foreign key to specific Message (NULL if session-level)
        filename: Sanitized filename used in filesystem storage
        original_filename: User's original filename for display
        file_path: Full path to file on disk (relative to storage root)
        content_type: MIME type (e.g., "application/pdf", "text/plain")
        file_size: File size in bytes
        file_hash: SHA-256 hash for deduplication and integrity checking
        uploaded_at: Timestamp when file was uploaded (UTC)
        meta_data: Additional file metadata as JSONB. Structure:
            {
                "extraction_status": "completed",  # Text extraction status
                "page_count": 10,  # For PDFs
                "language": "javascript",  # For code files
                "encoding": "utf-8"  # Character encoding
            }

    Relationships:
        session: Many-to-one with Session

    Note:
        CASCADE deletion ensures files are removed when parent session is deleted
        message_id is optional to support session-level file uploads that aren't tied to a specific message
    """

    __tablename__ = "files"

    __table_args__ = (
        CheckConstraint("(scope = 'session') = (session_id IS NOT NULL)", name="ck_files_session_scope"),
        Index(
            "uq_files_session_filename",
            "session_id",
            "filename",
            unique=True,
            postgresql_where=text("scope = 'session'"),
        ),
        Index(
            "uq_files_global_owner_filename",
            "owner_user_id",
            "filename",
            unique=True,
            postgresql_where=text("scope = 'global'"),
        ),
        Index(
            "uq_files_shared_tenant_filename",
            "tenant_id",
            "filename",
            unique=True,
            postgresql_where=text("scope = 'shared'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    session_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True
    )
    message_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=True
    )
    # ! Not a uuid FK: the auth-bypassed loopback principal owns uploads as "default" (api/deps.py)
    owner_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    session: Mapped[Optional["Session"]] = relationship(back_populates="files")
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)


class MessageFeedback(Base):
    """
    User feedback (thumbs up/down + optional note) on an assistant message

    One row per message (message_id is unique): re-voting updates the row, clearing the vote deletes it
    CASCADE-deleted with the parent message
    """

    __tablename__ = "message_feedback"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    message_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    rating: Mapped[str] = mapped_column(String(10), nullable=False)  # 'up' or 'down'
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    message: Mapped["Message"] = relationship(back_populates="feedback")


class Tenant(Base):
    """
    The isolation boundary: an organization whose users cannot observe another tenant's content

    A tenant contains users; groups inside it are the multi-membership axis and arrive with the auth work
    """

    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)


class User(Base):
    """
    Identity record
    password_hash is nullable by design: OIDC/JIT-provisioned users have no local credential
    """

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(10), nullable=False, default="user")
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    auth_sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)


class AuthSession(Base):
    """
    Server-side login session
    Only the sha256 of the token is stored; the raw token lives in the cookie
    """

    __tablename__ = "auth_sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="auth_sessions")


class LoginAttempt(Base):
    """
    Failed-login ledger backing the Postgres fixed-window rate limiter
    """

    __tablename__ = "login_attempts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    client_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class ApiKey(Base):
    """
    Server-granted service API key (ops scripts)
    Only the sha256 of the token is stored; the raw token is shown once at mint time
    """

    __tablename__ = "api_keys"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
