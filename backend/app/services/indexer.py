"""Indexing service: chunk files -> embeddings -> vector store.

Reads JSON chunk files from the chunked output directory, generates
dense embeddings, and upserts everything to the configured vector store
(which handles BM25 sparse vectors internally).

Designed for background execution via TaskManager - all methods accept
an optional task_id for progress reporting.

Usage:
    # From API endpoint (non-blocking):
    task_id = await task_manager.submit_task(
        "index_all", indexing_service.index_all_chunks
    )

    # Direct call:
    result = indexing_service.index_all_chunks()
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import config
from app.services.embeddings import embedding_service
from app.services.index_status_store import index_status_store

logger = logging.getLogger(__name__)

# * Batch size for embedding generation + upsert
EMBED_BATCH_SIZE = 128


class IndexingService:
    """Indexes code chunks into the vector store.

    Methods are BLOCKING (use via TaskManager for async execution).
    The store is resolved lazily on first use so the service can be
    instantiated before the store is connected.
    """

    def __init__(self):
        self._store = None

    def _get_store(self):
        """Lazy-load the vector store (must be connected already)."""
        if self._store is None:
            from app.services.vector_store import get_vector_store

            self._store = get_vector_store()
        return self._store

    def _update_progress(self, task_id: Optional[str], progress: float, message: str):
        """Update task progress if running in background."""
        if task_id:
            from app.services.task_manager import task_manager

            task_manager.update_progress(task_id, progress, message)

    def _collect_source_keys(self, chunks: list[dict[str, Any]]) -> set[str]:
        """Build stable identifiers for unique source files represented by chunks."""
        source_keys: set[str] = set()

        for chunk in chunks:
            source_file = str(chunk.get("source_file", "")).strip()
            if not source_file:
                continue

            source_keys.add(
                "::".join(
                    [
                        str(chunk.get("source_repo", "")).strip(),
                        str(chunk.get("edition", "")).strip(),
                        source_file,
                    ]
                )
            )

        return source_keys

    # =================================================================
    # Single file indexing
    # =================================================================

    def index_file(
        self,
        json_path: Path,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Load chunks from one JSON file and index them.

        BLOCKING - run via TaskManager for async execution.

        Args:
                json_path: Path to a chunk JSON file.
                task_id: Optional background task ID for progress.

        Returns:
                Dict with counts: chunks_loaded, embeddings_generated, points_uploaded.
        """
        import asyncio

        store = self._get_store()

        # Load chunks
        with open(json_path, "r", encoding="utf-8") as f:
            chunks = json.load(f)

        logger.info(f"Loaded {len(chunks)} chunks from {json_path.name}")
        self._update_progress(task_id, 0.1, f"Loaded {len(chunks)} chunks from {json_path.name}")
        source_keys = self._collect_source_keys(chunks)

        if not chunks:
            return {
                "chunks_loaded": 0,
                "embeddings_generated": 0,
                "points_uploaded": 0,
                "source_file": json_path.name,
                "_source_keys": [],
            }

        # Generate dense embeddings in batches
        texts = [chunk["content"] for chunk in chunks]
        all_embeddings = []

        for batch_start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch_end = min(batch_start + EMBED_BATCH_SIZE, len(texts))
            batch_texts = texts[batch_start:batch_end]

            batch_embeddings = embedding_service.embed_texts(batch_texts)
            all_embeddings.extend(batch_embeddings)

            progress = 0.1 + 0.5 * (batch_end / len(texts))
            self._update_progress(task_id, progress, f"Embedded {batch_end}/{len(texts)} chunks from {json_path.name}")

        logger.info(f"Generated {len(all_embeddings)} embeddings for {json_path.name}")

        # Upsert to vector store (store generates sparse vectors internally)
        loop = asyncio.new_event_loop()
        try:
            if not loop.run_until_complete(store.health_check()):
                connected = loop.run_until_complete(store.connect())
                if not connected:
                    raise RuntimeError("Vector store is not available")

            points_uploaded = loop.run_until_complete(store.upsert_chunks(chunks, all_embeddings))
        finally:
            loop.close()

        logger.info(f"Uploaded {points_uploaded} points from {json_path.name}")
        self._update_progress(task_id, 0.9, f"Uploaded {points_uploaded} vectors from {json_path.name}")

        return {
            "chunks_loaded": len(chunks),
            "embeddings_generated": len(all_embeddings),
            "points_uploaded": points_uploaded,
            "source_file": json_path.name,
            "_source_keys": sorted(source_keys),
        }

    # =================================================================
    # Full corpus indexing
    # =================================================================

    def index_all_chunks(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """Index all chunk files from the chunked output directory.

        BLOCKING - run via TaskManager for async execution.

        Reads all .json files from config.chunked_output_path and
        indexes them in sequence.

        Args:
                task_id: Optional background task ID for progress.

        Returns:
                Dict with total stats and per-file details.
        """
        output_dir = config.chunked_output_path

        if not output_dir.exists():
            raise FileNotFoundError(
                f"Chunked output directory not found: {output_dir}. Run the chunker first: python scripts/chunk_mpmb.py"
            )

        json_files = sorted(output_dir.glob("*.json"))

        if not json_files:
            raise FileNotFoundError(
                f"No JSON chunk files found in {output_dir}. Run the chunker first: python scripts/chunk_mpmb.py"
            )

        logger.info(f"Found {len(json_files)} chunk files to index")
        self._update_progress(task_id, 0.05, f"Found {len(json_files)} chunk files to index")

        results = []
        total_files = len(json_files)
        indexed_source_keys: set[str] = set()

        for i, json_file in enumerate(json_files, 1):
            logger.info(f"Indexing file {i}/{total_files}: {json_file.name}")

            result = self.index_file(json_file, task_id=None)  # Don't double-report
            indexed_source_keys.update(result.pop("_source_keys", []))
            results.append(result)

            # Update overall progress
            progress = 0.05 + 0.90 * (i / total_files)
            self._update_progress(
                task_id,
                progress,
                f"Indexed {i}/{total_files} chunk files ({result['points_uploaded']} vectors from {json_file.name})",
            )

        total_chunks = sum(r["chunks_loaded"] for r in results)
        total_uploaded = sum(r["points_uploaded"] for r in results)
        indexed_files = len(indexed_source_keys)
        completed_at = datetime.now(timezone.utc).isoformat()

        index_status_store.save(
            indexed_files=indexed_files,
            total_vectors=total_uploaded,
            status="ready",
            last_updated=completed_at,
        )

        self._update_progress(task_id, 1.0, f"Complete - {total_uploaded} vectors from {len(results)} chunk files")

        logger.info(f"Indexing complete: {total_uploaded} vectors from {len(results)} files ({total_chunks} chunks)")

        return {
            "status": "completed",
            "files_processed": indexed_files,
            "total_chunks_loaded": total_chunks,
            "total_points_uploaded": total_uploaded,
            "last_updated": completed_at,
            "details": results,
        }


# * Global instance
indexing_service = IndexingService()
