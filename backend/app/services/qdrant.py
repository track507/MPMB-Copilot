"""Qdrant vector database service"""
import logging
from typing import Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from qdrant_client.http.exceptions import UnexpectedResponse
from app.config import settings

logger = logging.getLogger(__name__)

class QdrantService:
	"""Qdrant vector database client wrapper"""

	def __init__(self):
		self.client: Optional[QdrantClient] = None
		self.collection_name = settings.qdrant_collection
		self.connected = False

	async def connect(self) -> bool:
		"""Initialize Qdrant client and ensure collection exists"""
		try:
			self.client = QdrantClient(
				host=settings.qdrant_host,
				port=settings.qdrant_port,
				timeout=settings.qdrant_timeout
			)

			# Test connection
			collections = self.client.get_collections()
			logger.info(f"Connected to Qdrant. Collections: {[c.name for c in collections.collections]}")

			# Create collection if it doesn't exist
			await self.ensure_collection()

			self.connected = True
			return True

		except Exception as e:
			logger.error(f"Failed to connect to Qdrant: {e}", exc_info=True)
			self.connected = False
			return False

	async def ensure_collection(self):
		"""Create collection if it doesn't exist"""
		try:
			self.client.get_collection(self.collection_name)
			logger.info(f"Collection '{self.collection_name}' already exists")
		except (UnexpectedResponse, Exception):
			logger.info(f"Creating collection '{self.collection_name}'")
			self.client.create_collection(
				collection_name=self.collection_name,
				vectors_config=VectorParams(
					size=settings.embedding_dimension,
					distance=Distance.COSINE
				)
			)
			logger.info(f"Collection '{self.collection_name}' created successfully")

	async def get_collection_info(self) -> dict:
		"""Get collection statistics"""
		if not self.client:
			return {"error": "Not connected"}

		try:
			info = self.client.get_collection(self.collection_name)
			# Based on CollectionInfo model from qdrant_client
			return {
				"name": self.collection_name,
				"points_count": info.points_count or 0,
				"indexed_vectors_count": info.indexed_vectors_count or 0,
				"segments_count": info.segments_count,
				"status": str(info.status),
			}
		except Exception as e:
			logger.error(f"Failed to get collection info: {e}", exc_info=True)
			return {"error": str(e)}

	async def health_check(self) -> bool:
		"""Check if Qdrant is accessible"""
		try:
			if not self.client:
				return False
			self.client.get_collections()
			return True
		except Exception:
			return False

# Global singleton instance
qdrant_service = QdrantService()
