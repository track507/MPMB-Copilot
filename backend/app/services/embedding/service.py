from dataclasses import dataclass
from typing import List, Optional, Protocol

from app.config import config
from app.logger import get_logger

logger = get_logger(__name__)


class EmbeddingProvider(Protocol):
    dimension: int

    def embed_texts(self, texts: List[str]) -> List[List[float]]: ...


@dataclass
class EmbeddingService:
    provider: Optional[EmbeddingProvider] = None

    def _load_provider(self) -> EmbeddingProvider:
        backend = config.embedding_provider  # "openai" | "ollama" | "fastembed" | "sbert"
        model = config.embedding_model

        if backend == "openai":
            from app.services.embedding.providers.openai import OpenAIEmbeddingProvider

            return OpenAIEmbeddingProvider(model=model, api_key=config.openai_api_key)

        if backend == "ollama":
            from app.services.embedding.providers.ollama import OllamaEmbeddingProvider

            return OllamaEmbeddingProvider(model=model, base_url=config.ollama_host)

        if backend == "fastembed":
            from app.services.embedding.providers.fastembed import FastEmbedProvider

            return FastEmbedProvider(model=model)

        if backend == "sbert":
            # Optional/legacy: only install sentence-transformers if you actually use it
            from app.services.embedding.providers.sbert import SBERTProvider

            return SBERTProvider(model=model)

        raise ValueError(f"Unknown embedding backend: {backend}")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if self.provider is None:
            self.provider = self._load_provider()
            logger.info(f"Embedding backend loaded: {type(self.provider).__name__} ({config.embedding_model})")

        return self.provider.embed_texts(texts)

    def identity(self) -> dict:
        """
        Identity of the embedding model that builds and queries the index

        Sourced from config (no model load) so it is cheap to call at startup and in the health check
        Used to stamp the vector collection and to detect a model change that would invalidate stored vectors
        """
        return {
            "provider": config.embedding_provider,
            "model": config.embedding_model,
            "dimension": config.embedding_dimension,
        }


embedding_service = EmbeddingService()
