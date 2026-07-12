"""Indexing API models

This module defines Pydantic models for the /index endpoint, which manages the
RAG (Retrieval-Augmented Generation) indexing pipeline for MPMB source code.

The indexing process:
1. Scans MPMB JavaScript source files
2. Splits code into semantic chunks with overlap
3. Generates embeddings for each chunk
4. Stores vectors in Qdrant for similarity search
5. Tracks metadata in PostgreSQL for retrieval

This enables the copilot to retrieve relevant MPMB code examples when answering
user questions about character sheet automation.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class IndexStatus(BaseModel):
    """Current status of the RAG vector index.

    Provides a snapshot of the indexed code corpus, including total vector count,
    number of source files indexed, and overall health status of the index.

    This model is returned by GET /index/status to allow monitoring of the
    indexing system and determining when re-indexing might be necessary.

    Attributes:
            collection_name: Name of the Qdrant collection storing vectors
                    (typically "mpmb_code_chunks")
            total_vectors: Total number of embedded code chunks in the vector database
            indexed_files: Number of unique MPMB source files that have been indexed
            last_updated: Timestamp of the most recent indexing operation (UTC).
                    None if no indexing has occurred yet.
            status: Index health status. Standard values:
                    - "ready": Index is current and ready for queries
                    - "indexing": Indexing operation in progress
                    - "stale": Index exists but source files have changed
                    - "empty": No vectors indexed yet
                    - "error": Indexing failed or index corrupted

    Example:
            >>> status = IndexStatus(
            ...     collection_name="mpmb_code_chunks",
            ...     total_vectors=1247,
            ...     indexed_files=42,
            ...     last_updated=datetime(2025, 1, 15, 10, 30, 0),
            ...     status="ready"
            ... )
            >>>
            >>> # Empty index example
            >>> empty = IndexStatus(
            ...     collection_name="mpmb_code_chunks",
            ...     total_vectors=0,
            ...     indexed_files=0,
            ...     last_updated=None,
            ...     status="empty"
            ... )
    """

    collection_name: str = Field(..., description="Qdrant collection name")
    total_vectors: int = Field(..., description="Total number of indexed code chunks")
    indexed_files: int = Field(..., description="Number of source files indexed")
    last_updated: Optional[datetime] = Field(None, description="Last indexing timestamp (UTC)")
    status: str = Field(..., description="Index health status (ready/indexing/stale/empty/error)")
    task_id: Optional[str] = Field(None, description="Active indexing task id when status is 'indexing'")


class IndexRequest(BaseModel):
    """Request to trigger indexing operation via POST /index.

    Initiates the RAG indexing pipeline to process MPMB source files and update
    the vector database. Can be configured to re-index existing files or only
    process new/modified files.

    The indexing process is typically asynchronous for large codebases, returning
    a task_id for status polling.

    Attributes:
            source_path: Path to MPMB source files to index. If None, uses the default
                    path configured in environment (typically /app/data/mpmb-source).
                    Can be absolute path or relative to project root.
            force_reindex: If True, re-process all files even if they haven't changed.
                    Useful after changing chunking strategy or embedding model.
                    If False (default), only processes new/modified files based on file hash.
            chunk_size: Override default chunk size (in characters). Must be 100-5000.
                    Larger chunks provide more context but may reduce retrieval precision.
                    Default is typically 1500 characters.
            chunk_overlap: Override default overlap between chunks (in characters).
                    Must be 0-1000. Overlap ensures context isn't lost at chunk boundaries.
                    Default is typically 200 characters (preserves function signatures).

    Example:
            >>> # Standard indexing request
            >>> request = IndexRequest()
            >>>
            >>> # Force re-index with custom chunking
            >>> reindex = IndexRequest(
            ...     force_reindex=True,
            ...     chunk_size=2000,
            ...     chunk_overlap=300
            ... )
            >>>
            >>> # Index specific directory
            >>> custom = IndexRequest(
            ...     source_path="/custom/mpmb/homebrew",
            ...     chunk_size=1000
            ... )

    Note:
            Chunk size and overlap significantly impact RAG quality:
            - Smaller chunks (500-1000): Better for specific API lookups
            - Larger chunks (2000-3000): Better for understanding complex patterns
            - Overlap (10-20%): Maintains context across boundaries

            Typical MPMB functions are 50-200 lines, so 1500 chars with 200 overlap
            usually captures complete function definitions.
    """

    source_path: Optional[str] = Field(None, description="Path to source files (default: configured MPMB source path)")
    force_reindex: bool = Field(False, description="Force re-indexing all files regardless of modification status")
    chunk_size: Optional[int] = Field(
        None, gt=100, le=5000, description="Chunk size in characters (100-5000, default: ~1500)"
    )
    chunk_overlap: Optional[int] = Field(
        None, ge=0, le=1000, description="Overlap between chunks in characters (0-1000, default: ~200)"
    )


class IndexResponse(BaseModel):
    """Response from indexing operation via POST /index.

    Returns the results of an indexing operation, including statistics about
    files processed, chunks created, and vectors uploaded to the database.

    For asynchronous indexing operations, includes a task_id that can be used
    to poll for completion status via GET /index/tasks/{task_id}.

    Attributes:
            status: Operation status. Values:
                    - "completed": Indexing finished successfully
                    - "in_progress": Async indexing started, use task_id to monitor
                    - "failed": Indexing encountered errors
                    - "partial": Some files indexed, others failed
            message: Human-readable status message with details about the operation.
                    For errors, includes diagnostic information.
            files_processed: Number of source files successfully processed and indexed
            chunks_created: Total number of code chunks created from processed files
            vectors_uploaded: Number of embeddings successfully uploaded to Qdrant.
                    Should equal chunks_created unless there were upload failures.
            task_id: Optional task identifier for async operations. Use this with
                    GET /index/tasks/{task_id} to check progress. None for synchronous ops.

    Example:
            >>> # Successful synchronous indexing
            >>> response = IndexResponse(
            ...     status="completed",
            ...     message="Successfully indexed 42 MPMB source files",
            ...     files_processed=42,
            ...     chunks_created=1247,
            ...     vectors_uploaded=1247,
            ...     task_id=None
            ... )
            >>>
            >>> # Async indexing started
            >>> async_response = IndexResponse(
            ...     status="in_progress",
            ...     message="Indexing started for 156 files",
            ...     files_processed=0,
            ...     chunks_created=0,
            ...     vectors_uploaded=0,
            ...     task_id="550e8400-e29b-41d4-a716-446655440000"
            ... )
            >>>
            >>> # Partial failure
            >>> partial = IndexResponse(
            ...     status="partial",
            ...     message="Indexed 40/42 files (2 parse errors)",
            ...     files_processed=40,
            ...     chunks_created=1180,
            ...     vectors_uploaded=1180,
            ...     task_id=None
            ... )

    Note:
            If vectors_uploaded < chunks_created, there was a problem with the
            Qdrant upload phase. Check logs for connection issues or quota limits.

            Typical indexing rates:
            - Small corpus (<50 files): Synchronous, ~5-10 seconds
            - Medium corpus (50-500 files): Async, ~1-5 minutes
            - Large corpus (>500 files): Async, ~10+ minutes
    """

    status: str = Field(..., description="Operation status (completed/in_progress/failed/partial)")
    message: str = Field(..., description="Human-readable status message")
    files_processed: int = Field(..., description="Number of files successfully indexed")
    chunks_created: int = Field(..., description="Total code chunks created")
    vectors_uploaded: int = Field(..., description="Embeddings uploaded to vector database")
    task_id: Optional[str] = Field(None, description="Task ID for async operations (use for status polling)")
