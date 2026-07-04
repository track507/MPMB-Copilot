"""Database models (SQLAlchemy ORM)

This module defines the core database schema for MPMB-Copilot using SQLAlchemy ORM.
Uses UUID7 for all primary keys to provide time-ordered identifiers with better
index performance than random UUID4.

Models:
    Session: Conversation/chat session
    Message: Individual messages within sessions
    File: Uploaded files attached to sessions
    DocumentChunk: Indexed code chunks for RAG retrieval
    MessageRetrieval: Junction table tracking which chunks informed each message
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, relationship
from uuid_utils import uuid7


class Base(DeclarativeBase):
    """Base class for all database models.

    Provides the declarative base for SQLAlchemy ORM models.
    All models inherit from this class to get ORM functionality.
    """

    pass


class Session(Base):
    """Conversation session model.

    Represents a single chat conversation containing multiple messages and files.
    Sessions use soft deletion (deleted_at) to preserve conversation history.

    The UUID7 primary key ensures sessions are naturally ordered by creation time,
    improving query performance when fetching recent conversations.

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
            Uses cascade="all, delete-orphan" to ensure when a session is deleted,
            all associated messages and files are automatically removed from the database.
    """

    __tablename__ = "sessions"

    id: UUID = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    title: str = Column(String(255), nullable=False, default="New Conversation")
    created_at: datetime = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    user_id: Optional[str] = Column(String(255), nullable=True)
    settings: dict = Column(JSONB, nullable=False, server_default="{}")
    meta_data: dict = Column(JSONB, nullable=False, server_default="{}")
    deleted_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    files = relationship("File", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    """Individual message within a conversation session.

    Stores message content, role (user/assistant/system), and comprehensive
    LLM usage metrics for cost tracking and performance monitoring.

    Messages are ordered within a session using sequence_number to ensure
    consistent conversation flow even if created_at timestamps are identical.

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
            retrievals: One-to-many with MessageRetrieval (tracks RAG sources)

    Note:
            CASCADE deletion ensures messages are removed when parent session is deleted.
            The cascade="all, delete-orphan" on retrievals ensures cleanup of RAG tracking.
    """

    __tablename__ = "messages"

    id: UUID = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    session_id: UUID = Column(PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    role: str = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    content: dict = Column(JSONB, nullable=False)
    created_at: datetime = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # LLM tracking
    provider: Optional[str] = Column(String(50), nullable=True)
    model: Optional[str] = Column(String(100), nullable=True)
    prompt_tokens: int = Column(Integer, default=0)
    completion_tokens: int = Column(Integer, default=0)
    total_tokens: int = Column(Integer, default=0)
    latency_ms: Optional[int] = Column(Integer, nullable=True)
    stop_reason: Optional[str] = Column(String(50), nullable=True)

    meta_data: dict = Column(JSONB, nullable=False, server_default="{}")
    sequence_number: int = Column(Integer, nullable=False)

    # Relationships
    session = relationship("Session", back_populates="messages")
    retrievals = relationship("MessageRetrieval", back_populates="message", cascade="all, delete-orphan")
    feedback = relationship(
        "MessageFeedback",
        back_populates="message",
        uselist=False,
        cascade="all, delete-orphan",
    )


class File(Base):
    """Uploaded file attachment model.

    Tracks files uploaded during conversations, storing both the original filename
    and the sanitized filesystem path. Files can be attached to entire sessions
    or specific messages.

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
            CASCADE deletion ensures files are removed when parent session is deleted.
            message_id is optional to support session-level file uploads that aren't
            tied to a specific message.
    """

    __tablename__ = "files"

    id: UUID = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    session_id: UUID = Column(PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    message_id: Optional[UUID] = Column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=True
    )

    filename: str = Column(String(255), nullable=False)
    original_filename: str = Column(String(255), nullable=False)
    file_path: str = Column(String(512), nullable=False)
    content_type: str = Column(String(100), nullable=False)
    file_size: int = Column(Integer, nullable=False)
    file_hash: Optional[str] = Column(String(64), nullable=True)
    uploaded_at: datetime = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    meta_data: dict = Column(JSONB, nullable=False, server_default="{}")

    # Relationships
    session = relationship("Session", back_populates="files")


class DocumentChunk(Base):
    """Document chunk model for RAG (Retrieval-Augmented Generation).

    Represents a chunked segment of source code indexed in the vector database
    for semantic search and retrieval. Each chunk is embedded and stored in
    Qdrant for similarity search.

    Chunks are created during the indexing process, where source files are split
    into overlapping segments to maintain context across chunk boundaries.

    Attributes:
            id: UUID7 primary key (time-ordered)
            source_file: Path to original source file (e.g., "src/common functions/SpellsList.js")
            chunk_index: Sequential index of this chunk within the source file (0-based)
            content: The actual text content of this chunk
            qdrant_id: UUID of corresponding vector in Qdrant collection (for sync)
            meta_data: Chunk metadata as JSONB. Structure:
                    {
                            "start_line": 150,  # Starting line number in source
                            "end_line": 200,  # Ending line number in source
                            "chunk_type": "function",  # Type of code (function/class/comment)
                            "language": "javascript",  # Programming language
                            "function_name": "AddSpell",  # Extracted context
                            "file_type": "spell"  # MPMB file category
                    }
            indexed_at: Timestamp when chunk was indexed (UTC)

    Relationships:
            message_retrievals: One-to-many with MessageRetrieval (tracks usage)

    Note:
            The qdrant_id is unique to ensure 1:1 mapping with vector database entries.
            CASCADE deletion on message_retrievals ensures cleanup when chunks are reindexed.
    """

    __tablename__ = "document_chunks"

    id: UUID = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    source_file: str = Column(String(512), nullable=False)
    chunk_index: int = Column(Integer, nullable=False)
    content: str = Column(Text, nullable=False)
    qdrant_id: Optional[str] = Column(String(255), unique=True, nullable=True)
    meta_data: dict = Column(JSONB, nullable=False, server_default="{}")
    indexed_at: datetime = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    message_retrievals = relationship("MessageRetrieval", back_populates="document_chunk", cascade="all, delete-orphan")


# ! Superseded by the meta_data["retrieval"] group on messages (agentic trace); this table + its document_chunks FK are unpopulated under agentic retrieval
class MessageRetrieval(Base):
    """Junction table tracking which document chunks were used for each message.

    Creates an audit trail of the RAG retrieval process, recording which code
    chunks were retrieved and used to generate each assistant response. This
    enables:
    - Source attribution and citation
    - RAG performance analysis
    - Retrieval quality monitoring
    - Cost/benefit analysis of chunk retrieval

    Attributes:
            id: UUID7 primary key (time-ordered)
            message_id: Foreign key to the Message that used this chunk
            document_chunk_id: Foreign key to the DocumentChunk that was retrieved
            rank: Retrieval ranking (1=most relevant, 2=second most, etc.)
            score: Similarity/relevance score from vector search (0.0-1.0)
            snippet: Optional truncated preview of the chunk for display
            created_at: Timestamp when retrieval was recorded (UTC)

    Relationships:
            message: Many-to-one with Message
            document_chunk: Many-to-one with DocumentChunk

    Note:
            CASCADE deletion ensures retrieval records are cleaned up when either
            the message or chunk is deleted. The rank field allows reconstructing
            the exact retrieval order for analysis.
    """

    __tablename__ = "message_retrievals"

    id: UUID = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    message_id: UUID = Column(PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    document_chunk_id: UUID = Column(
        PGUUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False
    )

    rank: int = Column(Integer, nullable=False)
    score: float = Column(Float, nullable=False)
    snippet: Optional[str] = Column(Text, nullable=True)
    created_at: datetime = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    message = relationship("Message", back_populates="retrievals")
    document_chunk = relationship("DocumentChunk", back_populates="message_retrievals")


class MessageFeedback(Base):
    """
    User feedback (thumbs up/down + optional note) on an assistant message

    One row per message (message_id is unique): re-voting updates the row, clearing the vote deletes it
    CASCADE-deleted with the parent message
    """

    __tablename__ = "message_feedback"

    id: UUID = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    message_id: UUID = Column(
        PGUUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    rating: str = Column(String(10), nullable=False)  # 'up' or 'down'
    note: Optional[str] = Column(Text, nullable=True)
    created_at: datetime = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    message = relationship("Message", back_populates="feedback")
