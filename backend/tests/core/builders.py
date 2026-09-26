"""
Test doubles for the domain's ports

Injection means a test supplies only the dependency it exercises, and the rest are inert stand-ins
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, cast

from app.core.intent import IntentClassifier
from app.core.retriever import Retriever
from app.core.storage_keys import DEFAULT_TENANT_ID
from app.core.tools.mpmb_tools import Deps
from app.services.documents.protocol import CachedDocument, CacheScope
from app.services.embedding.protocol import QueryEmbedder
from app.services.rerank.protocol import Reranker
from app.services.vector.protocol import VectorStore


def build_retriever(
    *,
    store: Any = None,
    embedder: Any = None,
    reranker: Any = None,
    classifier: Any = None,
) -> Retriever:
    """A Retriever wired with stand-ins, overriding only what a test cares about"""
    return Retriever(
        store=cast(VectorStore, store or SimpleNamespace()),
        embedder=cast(QueryEmbedder, embedder or SimpleNamespace(embed_query=lambda text: [0.0] * 8)),
        reranker=cast(
            Reranker, reranker or SimpleNamespace(rerank=lambda query, candidates, top_k: candidates[:top_k])
        ),
        classifier=cast(Any, classifier or SimpleNamespace(classify=lambda **kwargs: None)),
    )


def build_classifier(*, embedder: Any = None) -> IntentClassifier:
    """An IntentClassifier with an inert embedder, for the layers that never reach a centroid"""
    return IntentClassifier(
        embedder=cast(QueryEmbedder, embedder or SimpleNamespace(embed_query=lambda text: [0.0] * 8))
    )


class InertDocuments:
    """
    A document reader for tests whose files are all plain text
    """

    def lookup(self, path: Path, scope: CacheScope) -> Optional[CachedDocument]:
        return None

    def ensure_extracted(self, path: Path, scope: CacheScope) -> CachedDocument:
        raise AssertionError(f"this test did not expect an extraction: {path}")


def build_deps(**overrides: Any) -> Deps:
    """
    Deps with every required port filled by an inert stand-in

    A test names only what it exercises, so a new required field lands here rather than in every call site
    """
    defaults: dict[str, Any] = {
        "session_id": "sess-1",
        "edition": "2014",
        "tenant_id": DEFAULT_TENANT_ID,
        "documents": InertDocuments(),
    }
    return Deps(**{**defaults, **overrides})
