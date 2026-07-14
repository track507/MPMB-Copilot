"""Qdrant vector store implementation with hybrid search.

Implements the VectorStore protocol using Qdrant with:
        - Dense vectors (from configured embedding provider)
        - BM25 sparse vectors (via FastEmbed, IDF computed by Qdrant)
        - Reciprocal Rank Fusion for combining dense + sparse results
        - Payload indexes for edition, source_tier, chunk_type, object_type

Collection schema:
        Named vectors:
                "dense"  - 384-dim (or configured) cosine similarity
                "bm25"   - sparse, IDF-modified (Qdrant computes IDF server-side)
        Payload:
                content, source_file, source_repo, chunk_type, edition,
                source_tier, start_line, end_line, chunk_index, metadata.*
"""

from typing import Optional
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    HasIdCondition,
    MatchAny,
    MatchValue,
    Modifier,
    PayloadSchemaType,
    PointStruct,
    Prefetch,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from app.config import config
from app.logger import get_logger

logger = get_logger(__name__)

# * Reserved point holding the embedding-model stamp
# The nil UUID never collides with chunk ids (uuid4) and is excluded from every search via a must_not HasId condition in _build_qdrant_filter
_IDENTITY_POINT_ID = "00000000-0000-0000-0000-000000000000"
_IDENTITY_PAYLOAD_KEY = "_embedding_identity"

# Payload fields we create keyword indexes on for fast filtering
INDEXED_PAYLOAD_FIELDS = {
    "edition": PayloadSchemaType.KEYWORD,
    "source_tier": PayloadSchemaType.KEYWORD,
    "chunk_type": PayloadSchemaType.KEYWORD,
    "source_repo": PayloadSchemaType.KEYWORD,
    "metadata.object_type": PayloadSchemaType.KEYWORD,
    "metadata.object_key": PayloadSchemaType.KEYWORD,
    "metadata.function_name": PayloadSchemaType.KEYWORD,
    "metadata.category": PayloadSchemaType.KEYWORD,
    "metadata.attribute_name": PayloadSchemaType.KEYWORD,
}

# Full-text index for content search
FULLTEXT_PAYLOAD_FIELDS = [
    "content",
]


class QdrantStore:
    """Qdrant-backed vector store with hybrid search.

    Handles:
            - Collection lifecycle (create, delete, ensure indexes)
            - Batch upsert with dense + BM25 sparse vectors
            - Hybrid search (dense + sparse + metadata filters + RRF fusion)
            - Dense-only search as fallback
    """

    def __init__(self):
        from app.settings import settings

        self.client: Optional[QdrantClient] = None
        self.collection_name = config.qdrant_collection
        # Dimension follows the selected embedding model (catalog-derived); refreshed in _ensure_collection
        self.dense_dim = settings.embedding_dim()
        self._sparse_model = None  # Lazy-loaded BM25 model
        self._connected = False
        self._warned_missing_source_tier = False
        # Embedding-model stamp state, populated on connect() and after (re)indexing
        self._identity_status = "unknown"  # unknown | ok | missing | mismatch
        self._identity_message = ""
        self._has_identity_point = False
        # ? Chunker-version staleness is soft: stale chunks still serve queries, unlike a broken embedding stamp
        self._chunks_stale = False
        self._chunks_message = ""

    # BM25 sparse vector generation (lazy-loaded)

    def _get_sparse_model(self):
        """Lazy-load the FastEmbed BM25 sparse embedding model."""
        if self._sparse_model is None:
            from fastembed import SparseTextEmbedding

            # ? BM25 is token counting, not a neural model - it stays on CPU regardless of inference_device
            self._sparse_model = SparseTextEmbedding(
                model_name="Qdrant/bm25",
                threads=config.resolved_embedding_threads,
                cache_dir=str(config.fastembed_cache_path),
            )
            logger.info("Loaded BM25 sparse embedding model (Qdrant/bm25)")
        return self._sparse_model

    def _generate_sparse_vectors(self, texts: list[str]) -> list[SparseVector]:
        """Generate BM25 sparse vectors for a list of texts.

        FastEmbed produces the term-frequency weights; Qdrant's IDF
        modifier handles the inverse-document-frequency part server-side.
        """
        model = self._get_sparse_model()
        results = list(model.embed(texts))
        sparse_vectors = []
        for result in results:
            sparse_vectors.append(
                SparseVector(
                    indices=result.indices.tolist(),
                    values=result.values.tolist(),
                )
            )
        return sparse_vectors

    def _resolve_source_tier(self, chunk: dict) -> str:
        """Use the chunk's declared tier, or infer a safe fallback for older JSON."""
        source_tier = chunk.get("source_tier")
        if source_tier:
            return source_tier

        if not self._warned_missing_source_tier:
            logger.warning(
                "Chunk payloads are missing source_tier; inferring fallback tiers. "
                "Re-run chunking to refresh the JSON outputs."
            )
            self._warned_missing_source_tier = True

        source_file = str(chunk.get("source_file", "")).replace("/", "\\")
        source_repo = chunk.get("source_repo", "")

        if "additional content syntax" in source_file or "\\_functions\\" in source_file:
            return "authoritative"
        if source_file.startswith("_functions\\"):
            return "authoritative"
        if "\\_variables\\" in source_file or source_file.startswith("_variables\\"):
            return "official_example"
        if source_repo == "imports":
            if "WotC material" in source_file or "WotC 2024" in source_file:
                return "official_example"
            return "community_example"

        return "community_example"

    # * Connection and collection management

    async def connect(self) -> bool:
        """Initialize client, ensure collection and payload indexes exist."""
        try:
            self.client = QdrantClient(
                host=config.qdrant_host,
                port=config.qdrant_port,
                timeout=config.qdrant_timeout,
            )

            # Verify connection
            collections = self.client.get_collections()
            logger.info(
                f"Connected to Qdrant at {config.qdrant_host}:{config.qdrant_port}. "
                f"Collections: {[c.name for c in collections.collections]}"
            )

            await self._ensure_collection()
            await self._ensure_payload_indexes()
            await self._load_identity_state()
            self._connected = True
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}", exc_info=True)
            self._connected = False
            return False

    async def _ensure_collection(self):
        """Create the collection if it doesn't exist."""
        from app.settings import settings

        # ! Refresh so a reindex after an embedding-model change creates the collection with the new dimension
        self.dense_dim = settings.embedding_dim()
        try:
            self.client.get_collection(self.collection_name)
            logger.info(f"Collection '{self.collection_name}' exists")
        except (UnexpectedResponse, Exception):
            logger.info(f"Creating collection '{self.collection_name}'")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": VectorParams(
                        size=self.dense_dim,
                        distance=Distance.COSINE,
                    ),
                },
                sparse_vectors_config={
                    "bm25": SparseVectorParams(
                        modifier=Modifier.IDF,
                    ),
                },
            )
            logger.info(
                f"Collection '{self.collection_name}' created (dense={self.dense_dim}d cosine + BM25 sparse w/ IDF)"
            )

    async def _ensure_payload_indexes(self):
        """Create payload indexes for fast filtering if they don't exist."""
        for field_name, schema_type in INDEXED_PAYLOAD_FIELDS.items():
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=schema_type,
                )
            except Exception:
                # Index may already exist - that's fine
                pass

        for field_name in FULLTEXT_PAYLOAD_FIELDS:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=PayloadSchemaType.TEXT,
                )
            except Exception:
                pass

        logger.info(
            f"Payload indexes ensured for {len(INDEXED_PAYLOAD_FIELDS)} keyword fields "
            f"+ {len(FULLTEXT_PAYLOAD_FIELDS)} text fields"
        )

    # * Embedding-model identity stamp

    def read_identity(self) -> Optional[dict]:
        """Return the embedding stamp stored on the collection, or None if unstamped"""
        if not self.client:
            return None
        try:
            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[_IDENTITY_POINT_ID],
                with_payload=True,
            )
        except Exception:
            return None
        if not points:
            return None
        identity = (points[0].payload or {}).get(_IDENTITY_PAYLOAD_KEY)
        return identity if isinstance(identity, dict) else None

    async def write_identity(self, identity: dict) -> None:
        """
        Stamp the embedding-model identity onto the collection (reserved point)

        Called after (re)indexing so the stored vectors carry the model that built them
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")
        dim = int(identity.get("dimension") or self.dense_dim)
        # ? Cosine rejects the zero vector; a unit vector is fine since this point is never returned by search
        marker_vector = [1.0] + [0.0] * (dim - 1)
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=_IDENTITY_POINT_ID,
                    vector={"dense": marker_vector},
                    payload={_IDENTITY_PAYLOAD_KEY: identity},
                )
            ],
        )
        self._has_identity_point = True
        self._identity_status = "ok"
        self._identity_message = f"{identity.get('provider')}/{identity.get('model')} ({dim}d)"
        logger.info(f"Stamped embedding identity on '{self.collection_name}': {self._identity_message}")

    def _collection_dense_dim(self) -> Optional[int]:
        """Return the dimension the collection's dense vectors were created with, if readable"""
        try:
            vectors = self.client.get_collection(self.collection_name).config.params.vectors
            dense = vectors["dense"] if isinstance(vectors, dict) else vectors
            return getattr(dense, "size", None)
        except Exception:
            return None

    async def adopt_identity(self) -> tuple[bool, str]:
        """
        Stamp an existing collection with the current model in place, without re-embedding

        Used to upgrade a legacy (unstamped) index
        Only stamps when the stored vectors' dimension matches the configured model, so we never record a stamp that contradicts the actual vectors
        No-op if already stamped; refuses on a real mismatch
        """
        from app.services.embedding.service import embedding_service

        if not self.client:
            return False, "vector store not connected"

        if self.read_identity() is not None:
            if self._identity_status == "mismatch":
                return False, self._identity_message
            return True, "index already stamped"

        identity = embedding_service.identity()
        actual_dim = self._collection_dense_dim()
        if actual_dim is not None and actual_dim != identity["dimension"]:
            return False, (
                f"collection vectors are {actual_dim}d but configured model "
                f"{identity['provider']}/{identity['model']} is {identity['dimension']}d - force_reindex required"
            )
        await self.write_identity(identity)
        return (
            True,
            f"stamped existing index with {identity['provider']}/{identity['model']} ({identity['dimension']}d)",
        )

    async def _load_identity_state(self) -> None:
        """
        Compare the collection's embedding stamp against current config and cache the result

        Status: ok (match or empty/fresh), missing (populated but unstamped, legacy), mismatch (different model/dimension - stored vectors are incompatible)
        """
        from app.services.embedding.service import embedding_service

        current = embedding_service.identity()
        stored = self.read_identity()
        self._has_identity_point = stored is not None

        if stored is None:
            count = 0
            try:
                count = self.client.get_collection(self.collection_name).points_count or 0
            except Exception:
                pass
            if count == 0:
                self._identity_status = "ok"
                self._identity_message = "empty collection"
            else:
                self._identity_status = "missing"
                self._identity_message = "index predates identity stamping; re-index to enable model verification"
                logger.warning(
                    f"Qdrant collection '{self.collection_name}' is unstamped ({count} points). {self._identity_message}"
                )
            return

        stored_key = (stored.get("provider"), stored.get("model"), stored.get("dimension"))
        current_key = (current["provider"], current["model"], current["dimension"])
        if stored_key != current_key:
            self._identity_status = "mismatch"
            self._identity_message = (
                f"index built with {stored.get('provider')}/{stored.get('model')} ({stored.get('dimension')}d), "
                f"config is {current['provider']}/{current['model']} ({current['dimension']}d) - re-index required"
            )
            logger.error(f"Embedding model mismatch for '{self.collection_name}': {self._identity_message}")
            return

        self._identity_status = "ok"
        self._identity_message = f"{current['provider']}/{current['model']} ({current['dimension']}d)"

        # ? soft: a chunker-version mismatch means stale chunks (still queryable), not broken vectors
        from app.core.chunker import CHUNKER_VERSION

        stored_chunker = stored.get("chunker_version")
        if stored_chunker is not None and stored_chunker != CHUNKER_VERSION:
            self._chunks_stale = True
            self._chunks_message = f"chunks built by chunker v{stored_chunker}; current is v{CHUNKER_VERSION} - re-chunk + re-index recommended"
        else:
            self._chunks_stale = False
            self._chunks_message = ""

    def _raise_if_identity_mismatch(self) -> None:
        """Refuse dense/hybrid queries when stored vectors were built by a different model"""
        if self._identity_status == "mismatch":
            raise RuntimeError(f"Embedding model mismatch: {self._identity_message}")

    @property
    def chunks_stale(self) -> bool:
        return self._chunks_stale

    @property
    def chunks_message(self) -> str:
        return self._chunks_message

    async def identity_health(self) -> tuple[str, str]:
        """Map the cached embedding-stamp state to a (health_status, message) pair"""
        if self._identity_status == "mismatch":
            return "unavailable", self._identity_message
        if self._identity_status == "missing":
            return "ready", self._identity_message
        message = self._identity_message or f"{config.embedding_provider}/{config.embedding_model}"
        if self._chunks_stale:
            message = f"{message}; {self._chunks_message}"
        return "ready", message

    # * Upsert

    async def upsert_chunks(
        self,
        chunks: list[dict],
        dense_embeddings: list[list[float]],
        batch_size: int = 64,
    ) -> int:
        """Upload chunks with dense + sparse vectors to Qdrant.

        Generates BM25 sparse vectors internally from chunk content.
        Upserts in batches for memory efficiency.

        Args:
                chunks: Chunk dicts from the chunker JSON files.
                dense_embeddings: Pre-computed dense embeddings (same order).
                batch_size: Points per upsert call.

        Returns:
                Total number of points upserted.
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")

        if len(chunks) != len(dense_embeddings):
            raise ValueError(f"Chunk count ({len(chunks)}) != embedding count ({len(dense_embeddings)})")

        total_upserted = 0

        for batch_start in range(0, len(chunks), batch_size):
            batch_end = min(batch_start + batch_size, len(chunks))
            batch_chunks = chunks[batch_start:batch_end]
            batch_dense = dense_embeddings[batch_start:batch_end]

            # Generate BM25 sparse vectors for this batch
            batch_texts = [c["content"] for c in batch_chunks]
            batch_sparse = self._generate_sparse_vectors(batch_texts)

            # Build Qdrant points
            points = []
            for chunk, dense_vec, sparse_vec in zip(batch_chunks, batch_dense, batch_sparse):
                payload = {
                    "content": chunk["content"],
                    "source_file": chunk["source_file"],
                    "source_repo": chunk["source_repo"],
                    "chunk_type": chunk["chunk_type"],
                    "edition": chunk["edition"],
                    "source_tier": self._resolve_source_tier(chunk),
                    "start_line": chunk["start_line"],
                    "end_line": chunk["end_line"],
                    "chunk_index": chunk["chunk_index"],
                    "metadata": chunk.get("metadata", {}),
                }

                point = PointStruct(
                    id=str(uuid4()),
                    vector={
                        "dense": dense_vec,
                        "bm25": sparse_vec,
                    },
                    payload=payload,
                )
                points.append(point)

            # Upsert batch
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )

            total_upserted += len(points)
            logger.debug(f"Upserted batch {batch_start}-{batch_end} ({total_upserted}/{len(chunks)} total)")

        logger.info(f"Upserted {total_upserted} points to '{self.collection_name}'")
        return total_upserted

    # * Search

    def _build_qdrant_filter(self, filters: Optional[dict]) -> Optional[Filter]:
        """Convert a simple filter dict into a Qdrant Filter object.

        Supports top-level fields and nested metadata fields:
                {"edition": "2014", "source_tier": "authoritative"}
                {"object_type": "SpellsList"}  ->  metadata.object_type

        Always excludes the reserved embedding-identity point, so it returns a filter even when `filters` is empty
        """
        conditions = []

        # Map shorthand filter keys to actual payload paths
        field_map = {
            "edition": "edition",
            "source_tier": "source_tier",
            "chunk_type": "chunk_type",
            "source_repo": "source_repo",
            "object_type": "metadata.object_type",
            "object_key": "metadata.object_key",
            "function_name": "metadata.function_name",
            "category": "metadata.category",
            "attribute_name": "metadata.attribute_name",
        }

        for key, value in (filters or {}).items():
            field_path = field_map.get(key, key)

            if isinstance(value, list):
                # ! OR semantics: one condition matching ANY of the values
                # ! One must-condition per value would demand ALL of them at once, which can never match a single-valued payload field
                conditions.append(FieldCondition(key=field_path, match=MatchAny(any=list(value))))
            else:
                conditions.append(FieldCondition(key=field_path, match=MatchValue(value=value)))

        # ! Never return the reserved embedding-identity stamp as a search result
        return Filter(must=conditions or None, must_not=[HasIdCondition(has_id=[_IDENTITY_POINT_ID])])

    def _format_results(self, scored_points) -> list[dict]:
        """Convert Qdrant ScoredPoint objects to plain dicts."""
        results = []
        for point in scored_points:
            payload = point.payload or {}
            results.append(
                {
                    "id": point.id,
                    "score": point.score,
                    "content": payload.get("content", ""),
                    "source_file": payload.get("source_file", ""),
                    "source_repo": payload.get("source_repo", ""),
                    "chunk_type": payload.get("chunk_type", ""),
                    "edition": payload.get("edition", ""),
                    "source_tier": payload.get("source_tier", ""),
                    "start_line": payload.get("start_line", 0),
                    "end_line": payload.get("end_line", 0),
                    "chunk_index": payload.get("chunk_index", 0),
                    "metadata": payload.get("metadata", {}),
                }
            )
        return results

    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        filters: Optional[dict] = None,
        limit: int = 10,
        dense_limit: int = 20,
        sparse_limit: int = 20,
    ) -> list[dict]:
        """Hybrid search: dense + BM25 sparse, fused with RRF.

        Both dense and sparse sub-queries run in parallel via Qdrant's
        prefetch mechanism. Results are merged using Reciprocal Rank
        Fusion, which doesn't need score normalization.

        Args:
                query_text: Raw query for BM25 matching.
                query_embedding: Dense embedding of the query.
                filters: Optional metadata filters.
                limit: Final number of results after fusion.
                dense_limit: Candidates from dense search (before fusion).
                sparse_limit: Candidates from sparse search (before fusion).

        Returns:
                Fused results sorted by RRF score.
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")
        self._raise_if_identity_mismatch()

        # Generate BM25 sparse vector for the query
        sparse_vectors = self._generate_sparse_vectors([query_text])
        query_sparse = sparse_vectors[0]

        qdrant_filter = self._build_qdrant_filter(filters)

        results = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                Prefetch(
                    query=query_embedding,
                    using="dense",
                    limit=dense_limit,
                    filter=qdrant_filter,
                ),
                Prefetch(
                    query=query_sparse,
                    using="bm25",
                    limit=sparse_limit,
                    filter=qdrant_filter,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=limit,
            with_payload=True,
        )

        return self._format_results(results.points)

    async def dense_search(
        self,
        query_embedding: list[float],
        filters: Optional[dict] = None,
        limit: int = 10,
    ) -> list[dict]:
        """Dense-only vector search (no BM25 component)."""
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")
        self._raise_if_identity_mismatch()

        qdrant_filter = self._build_qdrant_filter(filters)

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            using="dense",
            limit=limit,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        return self._format_results(results.points)

    # * Collection management

    async def delete_collection(self) -> bool:
        """Delete and recreate the collection (loses all data)."""
        if not self.client:
            return False

        try:
            self.client.delete_collection(self.collection_name)
            logger.warning(f"Deleted collection '{self.collection_name}'")
            await self._ensure_collection()
            await self._ensure_payload_indexes()
            await self._load_identity_state()
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            return False

    async def collection_info(self) -> dict:
        """Return collection statistics."""
        if not self.client:
            return {"error": "Not connected"}

        try:
            info = self.client.get_collection(self.collection_name)
            # ? Don't count the reserved identity stamp as a chunk
            chunk_count = max((info.points_count or 0) - (1 if self._has_identity_point else 0), 0)
            return {
                "name": self.collection_name,
                "points_count": chunk_count,
                "vectors_count": chunk_count,
                "indexed_vectors_count": info.indexed_vectors_count or 0,
                "segments_count": info.segments_count,
                "status": str(info.status),
                "vectors": {
                    "dense": f"{self.dense_dim}d cosine",
                    "bm25": "sparse w/ IDF",
                },
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {"error": str(e)}

    async def health_check(self) -> bool:
        """Check if Qdrant is accessible."""
        try:
            if not self.client:
                return False
            self.client.get_collections()
            return True
        except Exception:
            return False
