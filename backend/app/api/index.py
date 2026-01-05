"""Indexing API endpoints (Non-blocking version)"""
import logging
from fastapi import APIRouter, HTTPException, status
from app.model.index import IndexStatus, IndexRequest, IndexResponse
from app.services.qdrant import qdrant_service
from app.services.indexer import indexing_service
from app.services.task_manager import task_manager
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

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

		if not qdrant_service.connected:
			return IndexStatus(
				collection_name=settings.qdrant_collection,
				total_vectors=0,
				indexed_files=0,
				last_updated=None,
				status="error"
			)

		collection_info = await qdrant_service.get_collection_info()

		if "error" in collection_info:
			return IndexStatus(
				collection_name=settings.qdrant_collection,
				total_vectors=0,
				indexed_files=0,
				last_updated=None,
				status="error"
			)

		points_count = collection_info.get('points_count', 0)
		index_status = "ready" if points_count > 0 else "empty"

		return IndexStatus(
			collection_name=settings.qdrant_collection,
			total_vectors=points_count,
			indexed_files=0,  # TODO: track in database
			last_updated=None,  # TODO: track in database
			status=index_status
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

		if not qdrant_service.connected:
			raise HTTPException(
				status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
				detail="Qdrant vector database is not available"
			)

		# Check if indexing already exists and force_reindex is False
		if not request.force_reindex:
			collection_info = await qdrant_service.get_collection_info()
			points_count = collection_info.get("points_count", 0)

			if points_count > 0:
				return IndexResponse(
					status="completed",
					message=f"Index already populated with {points_count} vectors. Use force_reindex=true to re-index.",
					files_processed=0,
					chunks_created=0,
					vectors_uploaded=points_count,
					task_id=None
				)

		# Submit indexing task to background task manager
		task_id = await task_manager.submit_task(
			name="index_all_chunks",
			func=indexing_service.index_all_chunks
		)

		logger.info(f"Indexing task submitted: {task_id}")

		return IndexResponse(
			status="in_progress",
			message=f"Indexing started in background. Poll GET /api/tasks/{task_id} for status.",
			files_processed=0,
			chunks_created=0,
			vectors_uploaded=0,
			task_id=task_id
		)

	except FileNotFoundError as e:
		logger.error(f"Chunk files not found: {e}")
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=str(e)
		)
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

		if not qdrant_service.connected:
			raise HTTPException(
				status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
				detail="Qdrant vector database is not available"
			)

		# Get current count before deletion
		collection_info = await qdrant_service.get_collection_info()
		current_count = collection_info.get("points_count", 0)

		# Delete and recreate collection
		qdrant_service.client.delete_collection(settings.qdrant_collection)
		await qdrant_service.ensure_collection()

		logger.info(f"Collection '{settings.qdrant_collection}' cleared")

		return {
			"status": "success",
			"message": f"Index cleared successfully. Deleted {current_count} vectors.",
			"deleted_count": current_count
		}

	except Exception as e:
		logger.error(f"Failed to clear index: {e}", exc_info=True)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Failed to clear index: {str(e)}",
		)
