"""
Vector store factory, and the only module that names a concrete store

The port lives in protocol.py, so the retriever and the indexer program against the type and never the client
Switching stores is one .env change, VECTOR_STORE: qdrant is the default, weaviate and pgvector are not built

Usage:
    store = get_vector_store()
    await store.connect()
    await store.upsert_chunks(chunks, embeddings)
    results = await store.hybrid_search(query_text, query_embedding, filters)
"""

from typing import Optional

from app.config import config
from app.logger import get_logger
from app.services.vector.protocol import VectorStore

logger = get_logger(__name__)
_store_instance: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """
    Return the configured store, constructed once and cached

    Reads VECTOR_STORE from config, and imports the client lazily so an unused one is never loaded
    """
    global _store_instance

    if _store_instance is not None:
        return _store_instance

    store_type = getattr(config, "vector_store", "qdrant")

    if store_type == "qdrant":
        from app.services.vector.qdrant import QdrantStore

        _store_instance = QdrantStore()
        return _store_instance

    # ? A second store adds a branch here, and the error below is the only other place that lists what is supported

    raise ValueError(f"Unknown vector store: {store_type}. Supported: qdrant. Set VECTOR_STORE in .env.")
