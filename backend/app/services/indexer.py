"""Indexing service for uploading chunks to Qdrant (Non-blocking version)"""
import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import uuid4
from qdrant_client.models import PointStruct
from app.services.qdrant import qdrant_service
from app.services.embeddings import embedding_service
from app.config import settings

logger = logging.getLogger(__name__)


class IndexingService:
	"""Index code chunks into Qdrant

	Note: These methods are designed to run in thread pool via TaskManager,
	so they use blocking I/O and synchronous operations.
	"""

	def index_chunks_from_json(
		self,
		json_path: Path,
		task_id: Optional[str] = None
	) -> Dict[str, Any]:
		"""Load chunks from JSON and index them

		This is a BLOCKING operation - use via TaskManager for async execution.
		"""
		# Import here to avoid circular dependency
		from app.services.task_manager import task_manager

		# Load chunks
		with open(json_path, 'r', encoding='utf-8') as f:
			chunks = json.load(f)

		logger.info(f"Loaded {len(chunks)} chunks from {json_path.name}")

		if task_id:
			task_manager.update_progress(task_id, 0.2, f"Loaded {len(chunks)} chunks from {json_path.name}")

		# Generate embeddings (BLOCKING - runs in thread pool)
		texts = [chunk['content'] for chunk in chunks]
		embeddings = embedding_service.embed_texts(texts)

		logger.info(f"Generated {len(embeddings)} embeddings")

		if task_id:
			task_manager.update_progress(task_id, 0.6, f"Generated {len(embeddings)} embeddings")

		# Create points for Qdrant
		points = []
		for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
			point = PointStruct(
				id=str(uuid4()),
				vector=embedding,
				payload={
					"content": chunk['content'],
					"source_file": chunk['source_file'],
					"chunk_index": chunk['chunk_index'],
					"start_line": chunk['start_line'],
					"end_line": chunk['end_line'],
					"chunk_type": chunk['chunk_type'],
					"metadata": chunk['metadata']
				}
			)
			points.append(point)

		# Upload to Qdrant (BLOCKING)
		qdrant_service.client.upsert(
			collection_name=settings.qdrant_collection,
			points=points
		)

		logger.info(f"Uploaded {len(points)} points to Qdrant")

		if task_id:
			task_manager.update_progress(task_id, 0.9, f"Uploaded {len(points)} vectors")

		return {
			"chunks_loaded": len(chunks),
			"embeddings_generated": len(embeddings),
			"points_uploaded": len(points),
			"source_file": json_path.name
		}

	def index_all_chunks(self, task_id: Optional[str] = None) -> Dict[str, Any]:
		"""Index all chunk files in the output directory

		This is a BLOCKING operation - use via TaskManager for async execution.
		"""
		# Import here to avoid circular dependency
		from app.services.task_manager import task_manager

		output_dir = Path(settings.data_dir) / "chunked_output"

		if not output_dir.exists():
			raise FileNotFoundError(f"Chunked output directory not found: {output_dir}")

		json_files = list(output_dir.glob("*.json"))

		if not json_files:
			raise FileNotFoundError(f"No JSON chunk files found in {output_dir}")

		logger.info(f"Found {len(json_files)} chunk files to index")

		if task_id:
			task_manager.update_progress(task_id, 0.1, f"Found {len(json_files)} files")

		results = []
		total_files = len(json_files)

		for i, json_file in enumerate(json_files, 1):
			logger.info(f"Processing file {i}/{total_files}: {json_file.name}")

			result = self.index_chunks_from_json(json_file, task_id=task_id)
			results.append(result)

			# Update overall progress
			if task_id:
				progress = 0.1 + (0.8 * i / total_files)
				task_manager.update_progress(
					task_id,
					progress,
					f"Indexed {i}/{total_files} files ({result['points_uploaded']} vectors)"
				)

		total_uploaded = sum(r['points_uploaded'] for r in results)

		if task_id:
			task_manager.update_progress(task_id, 1.0, f"Complete - {total_uploaded} vectors indexed")

		return {
			"status": "completed",
			"files_processed": len(results),
			"total_points_uploaded": total_uploaded,
			"details": results
		}


# Global instance
indexing_service = IndexingService()
