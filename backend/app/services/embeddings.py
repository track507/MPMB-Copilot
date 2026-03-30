import logging
from dataclasses import dataclass
from typing import List, Optional, Protocol

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    dimension: int

    def embed_texts(self, texts: List[str]) -> List[List[float]]: ...


@dataclass
class EmbeddingService:
    provider: Optional[EmbeddingProvider] = None

    def _load_provider(self) -> EmbeddingProvider:
        backend = settings.embedding_provider  # "openai" | "ollama" | "fastembed" | "sbert"
        model = settings.embedding_model

        if backend == "openai":
            from app.services.embedding_providers.openai import OpenAIEmbeddingProvider

            return OpenAIEmbeddingProvider(model=model, api_key=settings.openai_api_key)

        if backend == "ollama":
            from app.services.embedding_providers.ollama import OllamaEmbeddingProvider

            return OllamaEmbeddingProvider(model=model, base_url=settings.ollama_host)

        if backend == "fastembed":
            from app.services.embedding_providers.fastembed import FastEmbedProvider

            return FastEmbedProvider(model=model)

        if backend == "sbert":
            # Optional/legacy: only install sentence-transformers if you actually use it
            from app.services.embedding_providers.sbert import SBERTProvider

            return SBERTProvider(model=model)

        raise ValueError(f"Unknown embedding backend: {backend}")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if self.provider is None:
            self.provider = self._load_provider()
            logger.info(f"Embedding backend loaded: {type(self.provider).__name__} ({settings.embedding_model})")

        return self.provider.embed_texts(texts)


embedding_service = EmbeddingService()
