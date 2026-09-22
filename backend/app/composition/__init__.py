"""
The composition root: the one place concrete adapters are chosen and wired into the domain

Everything above it (api, main) asks here for a wired object
Nothing below it imports this package, which is what keeps the domain free of adapter choices

Built lazily rather than at import time, so importing a module never constructs a client
"""

from typing import Optional

from app.core.intent import IntentClassifier
from app.core.rag_engine import RAGEngine
from app.core.retriever import Retriever
from app.services.embedding.service import embedding_service
from app.services.llm.providers import build_model
from app.services.rerank.service import rerank_service
from app.services.vector.store import get_vector_store

_retriever: Optional[Retriever] = None
_rag_engine: Optional[RAGEngine] = None


def get_retriever() -> Retriever:
    """The wired retriever: vector store, query embedder, reranker and intent classifier"""
    global _retriever
    if _retriever is None:
        _retriever = Retriever(
            store=get_vector_store(),
            embedder=embedding_service,
            reranker=rerank_service,
            classifier=IntentClassifier(embedder=embedding_service),
        )
    return _retriever


def get_rag_engine() -> RAGEngine:
    """The wired agent loop, which hands the retriever to the tools through Deps"""
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RAGEngine(retriever=get_retriever(), model_factory=build_model)
    return _rag_engine


def reset() -> None:
    """
    Drop the wired objects so the next call rebuilds them

    For tests that swap an adapter, and for a settings change that picks a different provider
    """
    global _retriever, _rag_engine
    _retriever = None
    _rag_engine = None
