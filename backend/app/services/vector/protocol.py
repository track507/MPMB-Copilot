"""
The vector store port

Kept apart from store.py so the domain can name the type without importing the factory that builds a client
"""

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class VectorStore(Protocol):
    """
    Everything the retriever and the indexer are allowed to ask of a vector store

    Every method is async, and an implementation owns its connection, its sparse vectors and its query building
    """

    async def connect(self) -> bool:
        """
        Open the connection and make sure the collection and its indexes exist

        True means the store is ready to read and write
        """
        ...

    async def upsert_chunks(
        self,
        chunks: list[dict[str, Any]],
        dense_embeddings: list[list[float]],
    ) -> int:
        """
        Upload chunks with their dense embeddings and return how many points landed

        One embedding per chunk, in the same order
        Any further vectors, such as BM25 sparse ones, are the store's own business
        Chunk dicts are the chunker's JSON output: content, source_file, source_repo, chunk_type, edition
        The rest is source_tier, start_line, end_line and metadata
        """
        ...

    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        filters: Optional[dict[str, Any]] = None,
        limit: int = 10,
        dense_limit: int = 20,
        sparse_limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Fuse dense-vector and keyword matching into one ranked list, capped at limit

        dense_limit and sparse_limit are the per-branch prefetch ceilings before fusion
        filters matches chunk metadata exactly: edition ("2014" or "2024"), source_tier, chunk_type, object_type
        Each result carries content and a score where higher is better
        Its source_file, edition, source_tier and chunk_type ride along, with metadata nested
        """
        ...

    async def dense_search(
        self,
        query_embedding: list[float],
        filters: Optional[dict[str, Any]] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Search dense vectors only, skipping keyword matching

        Same filters and result shape as hybrid_search, and useful as a fallback or for a purely semantic query
        """
        ...

    async def write_identity(self, identity: dict[str, Any]) -> None:
        """
        Stamp the embedding provider, model and dimension onto the index

        Called after indexing, so stored vectors record the model that built them
        """
        ...

    async def identity_health(self) -> tuple[str, str]:
        """
        Report (status, message) for the stored embedding-model stamp

        "unavailable" means the stamp disagrees with the configured model, which only a re-index fixes
        """
        ...

    async def adopt_identity(self) -> tuple[bool, str]:
        """
        Stamp an existing unstamped index with the current model, without re-embedding

        Returns (stamped, message), and refuses when the stored vector dimension does not match the model
        """
        ...

    async def delete_collection(self) -> bool:
        """Delete the collection and recreate it empty, returning True on success"""
        ...

    async def collection_info(self) -> dict[str, Any]:
        """Return collection stats such as point count and index status"""
        ...

    async def health_check(self) -> bool:
        """Return True when the store is reachable and healthy"""
        ...
