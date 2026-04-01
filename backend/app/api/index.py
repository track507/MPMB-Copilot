"""Indexing API endpoints (Non-blocking version)"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from app.config import config
from app.model.index import IndexRequest, IndexResponse, IndexStatus
from app.services.index_status_store import index_status_store
from app.services.indexer import indexing_service
from app.services.task_manager import TaskStatus, task_manager
from app.services.vector_store import get_vector_store

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_ready_store():
    """Return the configured vector store, connecting on demand if needed."""
    store = get_vector_store()
    if await store.health_check():
        return store
    if await store.connect():
        return store
    return None


def _parse_last_updated(value: object) -> datetime | None:
    """Parse a persisted ISO timestamp into a datetime object."""
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        logger.warning(f"Invalid last_updated timestamp in index metadata: {value}")
        return None


def _has_active_index_task() -> bool:
    """Return True if a background indexing task is currently pending or running."""
    return any(
        task.name == "index_all_chunks" and task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}
        for task in task_manager.tasks.values()
    )


@router.get(
    "/index/status",
    response_model=IndexStatus,
    status_code=status.HTTP_200_OK,
    summary="Get Index Status",
    description="Retrieve current status of the vector database index",
)
async def get_index_status():
    """Get the current status of the vector database index

    This endpoint is NON-BLOCKING and returns immediately.
    """
    try:
        logger.debug("Index status requested")

        store = await _get_ready_store()
        if store is None:
            return IndexStatus(
                collection_name=config.qdrant_collection,
                total_vectors=0,
                indexed_files=0,
                last_updated=None,
                status="error",
            )

        collection_info = await store.collection_info()

        if "error" in collection_info:
            return IndexStatus(
                collection_name=config.qdrant_collection,
                total_vectors=0,
                indexed_files=0,
                last_updated=None,
                status="error",
            )

        points_count = collection_info.get("points_count", 0)
        metadata = index_status_store.load()
        if not metadata and points_count > 0:
            metadata = index_status_store.rebuild_from_chunked_output(total_vectors=points_count, status="ready")

        if _has_active_index_task():
            index_status = "indexing"
        else:
            index_status = "ready" if points_count > 0 else "empty"

        return IndexStatus(
            collection_name=config.qdrant_collection,
            total_vectors=points_count,
            indexed_files=int(metadata.get("indexed_files", 0)),
            last_updated=_parse_last_updated(metadata.get("last_updated")),
            status=index_status,
        )

    except Exception as e:
        logger.error(f"Failed to get index status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve index status: {str(e)}",
        )


@router.post(
    "/index",
    response_model=IndexResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Index MPMB Source Code",
    description="Start indexing MPMB source files in background (non-blocking)",
)
async def trigger_indexing(request: IndexRequest = IndexRequest()):
    """Trigger background indexing of MPMB source code

    This endpoint starts a BACKGROUND TASK and returns immediately with a task_id.
    Use GET /api/tasks/{task_id} to poll for completion status.

    The server remains fully responsive during indexing.
    """
    try:
        logger.info("Indexing request received")
        logger.info(f"Force reindex: {request.force_reindex}")

        store = await _get_ready_store()
        if store is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Vector store is not available")

        # Check if indexing already exists and force_reindex is False
        if not request.force_reindex:
            collection_info = await store.collection_info()
            points_count = collection_info.get("points_count", 0)

            if points_count > 0:
                return IndexResponse(
                    status="completed",
                    message=f"Index already populated with {points_count} vectors. Use force_reindex=true to re-index.",
                    files_processed=0,
                    chunks_created=0,
                    vectors_uploaded=points_count,
                    task_id=None,
                )

        # Submit indexing task to background task manager
        task_id = await task_manager.submit_task(name="index_all_chunks", func=indexing_service.index_all_chunks)

        logger.info(f"Indexing task submitted: {task_id}")

        return IndexResponse(
            status="in_progress",
            message=f"Indexing started in background. Poll GET /api/tasks/{task_id} for status.",
            files_processed=0,
            chunks_created=0,
            vectors_uploaded=0,
            task_id=task_id,
        )

    except FileNotFoundError as e:
        logger.error(f"Chunk files not found: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start indexing: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start indexing: {str(e)}",
        )


@router.delete(
    "/index",
    status_code=status.HTTP_200_OK,
    summary="Clear Index",
    description="Delete all vectors from the Qdrant collection",
)
async def clear_index():
    """Clear all vectors from the Qdrant collection

    WARNING: This operation cannot be undone.
    All indexed vectors will be permanently deleted.
    """
    try:
        logger.warning("Index clear requested - deleting all vectors")

        store = await _get_ready_store()
        if store is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Vector store is not available")

        # Get current count before deletion
        collection_info = await store.collection_info()
        current_count = collection_info.get("points_count", 0)

        # Delete and recreate collection
        deleted = await store.delete_collection()
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to clear vector collection",
            )

        logger.info(f"Collection '{config.qdrant_collection}' cleared")
        index_status_store.clear()

        return {
            "status": "success",
            "message": f"Index cleared successfully. Deleted {current_count} vectors.",
            "deleted_count": current_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear index: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear index: {str(e)}",
        )
