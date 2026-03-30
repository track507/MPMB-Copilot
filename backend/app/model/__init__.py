"""Pydantic models and database models"""

# API Models
from app.model.chat import ChatRequest, ChatResponse, ChatStreamChunk

# Database Models
from app.model.database import (
    Base,
    DocumentChunk,
    File,
    Message,
    MessageRetrieval,
    Session,
)
from app.model.health import HealthResponse, ServiceStatus
from app.model.index import IndexRequest, IndexResponse, IndexStatus

# LLM Models
from app.model.llm import (
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
)

# RAG Models
from app.model.rag import (
    CodeChunk,
    EmbeddingRequest,
    EmbeddingResponse,
    RAGContext,
    RetrievalMetadata,
    VectorSearchResult,
)

# Task Models
from app.model.task import (
    TaskListResponse,
    TaskStatusResponse,
)

__all__ = [
    # Health models
    "HealthResponse",
    "ServiceStatus",
    # Chat models
    "ChatRequest",
    "ChatResponse",
    "ChatStreamChunk",
    # Index models
    "IndexStatus",
    "IndexRequest",
    "IndexResponse",
    # RAG models
    "CodeChunk",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "VectorSearchResult",
    "RAGContext",
    "RetrievalMetadata",
    # LLM models
    "LLMProvider",
    "LLMMessage",
    "LLMRequest",
    "LLMResponse",
    "LLMStreamChunk",
    # Database models
    "Base",
    "Session",
    "Message",
    "File",
    "DocumentChunk",
    "MessageRetrieval",
    # Task models
    "TaskListResponse",
    "TaskStatusResponse",
]
