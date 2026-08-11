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
    _selection: Optional[tuple[str, str]] = None

    def _load_provider(self) -> EmbeddingProvider:
        from app.settings import settings

        backend = settings.embedding_provider  # "openai" | "ollama" | "fastembed" | "sbert"
        model = settings.embedding_model

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

    def _ensure_provider(self) -> EmbeddingProvider:
        from app.core.onnx_device import effective_device
        from app.settings import settings

        # * Reload when the embedding selection changes so a settings switch (or a GPU fallback) takes effect
        selection = (settings.embedding_provider, settings.embedding_model, effective_device())
        if self.provider is None or self._selection != selection:
            self.provider = self._load_provider()
            self._selection = selection
            logger.info(
                f"Embedding backend loaded: {type(self.provider).__name__} ({selection[1]}, device={selection[2]})"
            )
        return self.provider

    def _embed(self, payload: List[str]) -> List[List[float]]:
        """
        Embed a batch, demoting the whole process to CPU if the GPU faults

        A DirectML/CUDA device hang (Windows TDR resets a GPU whose dispatch outran the watchdog) would otherwise fail a long re-index outright; retrying on CPU costs time, not the run
        """
        from app.core.onnx_device import force_cpu_fallback, is_device_failure

        try:
            return self._ensure_provider().embed_texts(payload)
        except Exception as e:
            if not (is_device_failure(e) and force_cpu_fallback(str(e))):
                raise
            # _ensure_provider reloads on CPU because effective_device() now reports "cpu"
            return self._ensure_provider().embed_texts(payload)

    def _prefixes(self) -> tuple[str, str]:
        # (query_prefix, doc_prefix) for the current model; empty for non-prefix models
        from app.core.embedding_catalog import get_entry
        from app.settings import settings

        entry = get_entry(settings.embedding_provider, settings.embedding_model)
        return (entry.query_prefix, entry.doc_prefix) if entry else ("", "")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        # Raw passthrough (no prefixes); kept for internal callers
        return self._embed(texts)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        _, doc_prefix = self._prefixes()
        payload = [doc_prefix + t for t in texts] if doc_prefix else texts
        return self._embed(payload)

    def embed_query(self, text: str) -> List[float]:
        query_prefix, _ = self._prefixes()
        payload = query_prefix + text if query_prefix else text
        return self._embed([payload])[0]

    def identity(self) -> dict:
        """
        Identity of the selected embedding model

        Provider/model come from settings, dimension from the catalog (no model load) so it is cheap to call at startup and in the health check
        Used to stamp the vector collection and to detect a model change that would invalidate stored vectors
        """
        from app.core.embedding_catalog import dimension_for
        from app.settings import settings

        provider = settings.embedding_provider
        model = settings.embedding_model
        return {
            "provider": provider,
            "model": model,
            "dimension": dimension_for(provider, model),
        }


embedding_service = EmbeddingService()
