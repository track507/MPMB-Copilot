"""External service integrations.

Re-exports public symbols from subpackages for convenience.
"""

from app.services.db import db, session_service
from app.services.embedding import embedding_service
from app.services.indexing import index_status_store, indexing_service
from app.services.llm import llm_client
from app.services.task_manager import task_manager
from app.services.vector import VectorStore, get_vector_store

__all__ = [
    "db",
    "session_service",
    "get_vector_store",
    "VectorStore",
    "embedding_service",
    "indexing_service",
    "index_status_store",
    "llm_client",
    "task_manager",
]
