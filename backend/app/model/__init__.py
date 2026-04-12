"""Pydantic models and database models.

Re-exports all public symbols so existing `from app.model import X`
statements continue to work after the directory reorganization.
"""

# Database ORM Models
from app.model.orm import (
    Base,
    DocumentChunk,
    File,
    Message,
    MessageRetrieval,
    Session,
)

# API Schemas
from app.model.schemas.chat import ChatRequest, ChatResponse, ChatStreamChunk
from app.model.schemas.health import HealthResponse, ServiceStatus
from app.model.schemas.index import IndexRequest, IndexResponse, IndexStatus
from app.model.schemas.session import (
    MessageOut,
    SessionCreate,
    SessionDetailOut,
    SessionListOut,
    SessionOut,
    SessionUpdate,
)
from app.model.schemas.task import (
    TaskListResponse,
    TaskStatusResponse,
)

__all__ = [
    # ORM models
    "Base",
    "Session",
    "Message",
    "File",
    "DocumentChunk",
    "MessageRetrieval",
    # Health
    "HealthResponse",
    "ServiceStatus",
    # Chat
    "ChatRequest",
    "ChatResponse",
    "ChatStreamChunk",
    # Index
    "IndexStatus",
    "IndexRequest",
    "IndexResponse",
    # Session
    "SessionCreate",
    "SessionUpdate",
    "SessionOut",
    "SessionDetailOut",
    "SessionListOut",
    "MessageOut",
    # Task
    "TaskListResponse",
    "TaskStatusResponse",
]
