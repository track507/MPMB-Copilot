"""
The composition root: the one place concrete adapters are chosen and wired into the domain

Everything above it (api, main) asks here for a wired object
Nothing below it imports this package, which is what keeps the domain free of adapter choices

Built lazily rather than at import time, so importing a module never constructs a client
"""

from typing import Optional

from app.config import config
from app.core.intent import IntentClassifier
from app.core.rag_engine import RAGEngine
from app.core.retriever import Retriever
from app.services.compute.threads import ThreadLane
from app.services.documents import service as documents_service
from app.services.embedding.service import embedding_service
from app.services.jobs.local import LocalJobRunner
from app.services.llm.providers import build_model
from app.services.rerank.service import rerank_service
from app.services.source_catalog import source_catalog_service
from app.services.vector.store import get_vector_store

_retriever: Optional[Retriever] = None
_rag_engine: Optional[RAGEngine] = None
_job_runner: Optional[LocalJobRunner] = None
# ! Process-lifetime: reset() does not drop it
_interactive: Optional[ThreadLane] = None


def _interactive_lane() -> ThreadLane:
    global _interactive
    if _interactive is None:
        _interactive = ThreadLane("interactive", config.interactive_workers)
    return _interactive


def get_retriever() -> Retriever:
    """The wired retriever: vector store, query embedder, reranker and intent classifier"""
    global _retriever
    if _retriever is None:
        _retriever = Retriever(
            store=get_vector_store(),
            embedder=embedding_service,
            reranker=rerank_service,
            classifier=IntentClassifier(embedder=embedding_service),
            compute=_interactive_lane(),
        )
    return _retriever


def warm() -> None:
    """Load the query-path models"""
    get_retriever().warm()


def get_job_runner() -> LocalJobRunner:
    global _job_runner
    if _job_runner is None:
        _job_runner = LocalJobRunner(
            {},
            lane=ThreadLane("job", config.job_workers),
            per_tenant=config.jobs_per_tenant,
        )
    return _job_runner


def get_rag_engine() -> RAGEngine:
    """The wired agent loop, which hands the retriever to the tools through Deps"""
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RAGEngine(
            retriever=get_retriever(),
            model_factory=build_model,
            catalog=source_catalog_service.snapshot,
            # ? The service module satisfies DocumentReader structurally; no wrapper class is needed
            documents=documents_service,
        )
    return _rag_engine


def reset() -> None:
    """
    Drop the wired objects so the next call rebuilds them

    For tests that swap an adapter, and for a settings change that picks a different provider
    """
    global _retriever, _rag_engine
    _retriever = None
    _rag_engine = None
