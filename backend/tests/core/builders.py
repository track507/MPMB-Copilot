"""
Test doubles for the domain's ports

Injection means a test supplies only the dependency it exercises, and the rest are inert stand-ins
"""

from types import SimpleNamespace
from typing import Any, cast

from app.core.intent import IntentClassifier
from app.core.retriever import Retriever
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
