"""Vector store abstraction layer.

Defines the VectorStore protocol that all store implementations must follow.
The retriever and indexer program against this interface, never against a
concrete store. Switching stores is a one-line .env change:

    VECTOR_STORE=qdrant     # default
    VECTOR_STORE=weaviate   # future
    VECTOR_STORE=pgvector   # future

Usage:
    from app.services.vector import get_vector_store
    store = get_vector_store()       # returns the configured implementation
    await store.connect()
    await store.upsert_chunks(chunks, embeddings)
    results = await store.hybrid_search(query_text, query_embedding, filters)
"""

from typing import Optional, Protocol, runtime_checkable

from app.config import config
from app.logger import get_logger

logger = get_logger(__name__)
_store_instance: Optional["VectorStore"] = None


@runtime_checkable
class VectorStore(Protocol):
    """Protocol defining the vector store interface.

    All methods are async. Implementations handle their own connection
    management, sparse vector generation, and provider-specific query
    building internally.
    """

    async def connect(self) -> bool:
        """Initialize connection and ensure collection/index exists.

        Returns True if connection succeeded and collection is ready.
        """
        ...

    async def upsert_chunks(
        self,
        chunks: list[dict],
        dense_embeddings: list[list[float]],
    ) -> int:
        """Upload chunks with their dense embeddings to the store.

        The store is responsible for generating any additional vectors
        (e.g. BM25 sparse vectors) from the chunk content internally.

        Args:
                chunks: List of chunk dicts (from chunker JSON output).
                        Each has: content, source_file, source_repo, chunk_type,
                        edition, source_tier, start_line, end_line, metadata.
                dense_embeddings: One dense embedding per chunk, same order.

        Returns:
                Number of points successfully upserted.
        """
        ...

    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        filters: Optional[dict] = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search using both dense vectors and keyword/BM25 matching.

        Combines semantic similarity with lexical matching and fuses
        results (e.g. via Reciprocal Rank Fusion).

        Args:
                query_text: Raw query string (used for BM25/keyword matching).
                query_embedding: Dense embedding of the query.
                filters: Optional metadata filters. Keys can include:
                        - edition: "2014" | "2024"
                        - source_tier: "authoritative" | "official_example" | "community_example"
                        - chunk_type: "object_literal" | "function_call" | etc.
                        - object_type: "SpellsList" | "FeatsList" | etc.
                limit: Max results to return.

        Returns:
                List of result dicts, each with:
                        - content: chunk text
                        - score: relevance score (higher = better)
                        - source_file, edition, source_tier, chunk_type
                        - metadata: nested metadata dict
        """
        ...

    async def dense_search(
        self,
        query_embedding: list[float],
        filters: Optional[dict] = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search using only dense vectors (no keyword matching).

        Useful as a fallback or for queries that are purely semantic.
        Same filter/return format as hybrid_search.
        """
        ...

    async def write_identity(self, identity: dict) -> None:
        """Stamp the embedding-model identity (provider/model/dimension) onto the index.

        Called after (re)indexing so stored vectors record the model that built them.
        """
        ...

    async def identity_health(self) -> tuple[str, str]:
        """Return (health_status, message) for the stored embedding-model stamp.

        "unavailable" signals a model/dimension mismatch that requires a re-index.
        """
        ...

    async def adopt_identity(self) -> tuple[bool, str]:
        """Stamp an existing unstamped index with the current model in place (no re-embed).

        Returns (stamped, message). Refuses if the stored vector dimension doesn't
        match the configured model.
        """
        ...

    async def delete_collection(self) -> bool:
        """Delete and recreate the collection. Returns True on success."""
        ...

    async def collection_info(self) -> dict:
        """Return collection stats (point count, index status, etc.)."""
        ...

    async def health_check(self) -> bool:
        """Return True if the store is reachable and healthy."""
        ...


def get_vector_store() -> VectorStore:
    """Factory: return the configured vector store implementation.

    Reads VECTOR_STORE from config and returns a cached singleton.
    """
    global _store_instance

    if _store_instance is not None:
        return _store_instance

    store_type = getattr(config, "vector_store", "qdrant")

    if store_type == "qdrant":
        from app.services.vector.qdrant import QdrantStore

        _store_instance = QdrantStore()
        return _store_instance

    # Future implementations:
    # elif store_type == "weaviate":
    #     from app.services.weaviate_store import WeaviateStore
    #     return WeaviateStore()
    # elif store_type == "pgvector":
    #     from app.services.pgvector_store import PgVectorStore
    #     return PgVectorStore()

    raise ValueError(f"Unknown vector store: {store_type}. Supported: qdrant. Set VECTOR_STORE in .env.")
