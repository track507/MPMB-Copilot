"""
Cross-encoder reranker service (local fastembed)

Lazy singleton mirroring embedding_service: loads the configured TextCrossEncoder on first use,
reloads when the settings selection changes, and degrades gracefully - any failure or a
non-fastembed provider falls back to the input order so a rerank problem never breaks a search
"""

from dataclasses import dataclass
from typing import Optional

from app.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RerankService:
    _model: object | None = None
    _selection: Optional[tuple[str, str]] = None

    def _ensure_model(self) -> object | None:
        from app.settings import settings

        selection = (settings.rerank_provider, settings.rerank_model)
        # ? Cache per selection; a cached None means "known-unavailable", so we don't reload every call
        if self._selection == selection:
            return self._model

        self._selection = selection
        self._model = None

        # ! Only the bundled fastembed provider is wired now; sbert/cloud are catalog stubs for the store
        if settings.rerank_provider != "fastembed":
            logger.warning(f"Rerank provider '{settings.rerank_provider}' unavailable; reranking disabled")
            return None

        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            from app.config import config

            self._model = TextCrossEncoder(model_name=settings.rerank_model, cache_dir=str(config.fastembed_cache_path))
            logger.info(f"Reranker loaded: {settings.rerank_model}")
        except Exception as e:
            logger.warning(f"Reranker load failed ({e}); reranking disabled")
            self._model = None
        return self._model

    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        if not candidates:
            return []
        model = self._ensure_model()
        if model is None:
            return candidates[:top_k]
        try:
            docs = [c.get("content", "") for c in candidates]
            scores = list(model.rerank(query, docs))
            ranked = sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)
            return [{**cand, "rerank_score": float(score)} for cand, score in ranked[:top_k]]
        except Exception as e:  # ! never break a search on a rerank failure
            logger.warning(f"Rerank failed ({e}); falling back to fused order")
            self._selection = None  # ? force a fresh load attempt next call
            return candidates[:top_k]


rerank_service = RerankService()
