"""Indexing service for uploading chunks to Qdrant"""
import logging
import json
from pathlib import Path
from typing import Dict, Any
from uuid import uuid4
from qdrant_client.models import PointStruct
from app.services.qdrant import qdrant_service
from app.services.embeddings import embedding_service
from app.config import settings

logger = logging.getLogger(__name__)

class IndexingService:
    """Index code chunks into Qdrant"""

    async def index_chunks_from_json(self, json_path: Path) -> Dict[str, Any]:
        """Load chunks from JSON and index them"""

        # Load chunks
        with open(json_path, 'r', encoding='utf-8') as f:
            chunks = json.load(f)

        logger.info(f"Loaded {len(chunks)} chunks from {json_path.name}")

        # Generate embeddings
        texts = [chunk['content'] for chunk in chunks]
        embeddings = embedding_service.embed_texts(texts)

        logger.info(f"Generated {len(embeddings)} embeddings")

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

        # Upload to Qdrant
        qdrant_service.client.upsert(
            collection_name=settings.qdrant_collection,
            points=points
        )

        logger.info(f"Uploaded {len(points)} points to Qdrant")

        return {
            "chunks_loaded": len(chunks),
            "embeddings_generated": len(embeddings),
            "points_uploaded": len(points),
            "source_file": json_path.name
        }

    async def index_all_chunks(self) -> Dict[str, Any]:
        """Index all chunk files in the output directory"""
        output_dir = Path(settings.data_dir) / "chunked_output"

        results = []
        for json_file in output_dir.glob("*.json"):
            result = await self.index_chunks_from_json(json_file)
            results.append(result)

        total_uploaded = sum(r['points_uploaded'] for r in results)

        return {
            "status": "completed",
            "files_processed": len(results),
            "total_points_uploaded": total_uploaded,
            "details": results
        }

# Global instance
indexing_service = IndexingService()
