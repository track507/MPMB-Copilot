"""Embedding generation service using sentence-transformers"""
import logging
from typing import List
from sentence_transformers import SentenceTransformer
from app.config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    """Generate embeddings for code chunks"""

    def __init__(self):
        self.model = None
        self.model_name = settings.embedding_model
        self.dimension = settings.embedding_dimension

    def load_model(self):
        """Load the embedding model"""
        logger.info(f"Loading embedding model: {self.model_name}")
        self.model = SentenceTransformer(self.model_name)
        logger.info(f"Model loaded. Dimension: {self.model.get_sentence_embedding_dimension()}")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts"""
        if not self.model:
            self.load_model()

        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def embed_single(self, text: str) -> List[float]:
        """Generate embedding for a single text"""
        return self.embed_texts([text])[0]

# Global instance
embedding_service = EmbeddingService()
