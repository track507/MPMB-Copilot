import threading
from types import SimpleNamespace

import pytest

from app.core.catalog import EMPTY_CATALOG
from app.core.intent import IntentResult, QueryIntent
from app.core.storage_keys import DEFAULT_TENANT_ID
from app.services.compute.threads import ThreadLane
from tests.core.builders import InlineLane, build_retriever

_INTENT = IntentResult(
    primary=QueryIntent.LOOKUP, secondary=None, confidence=0.9, margin=0.5, is_blended=False, method="stub"
)


class _Store:
    async def hybrid_search(self, query_text, query_embedding, *, tenant_id, filters=None, **kwargs):
        return [{"id": "a", "content": "a", "source_tier": "authoritative"}]


def _recording(threads: set[int]):
    def record(value):
        threads.add(threading.get_ident())
        return value

    embedder = SimpleNamespace(embed_query=lambda text: record([0.0] * 8))
    classifier = SimpleNamespace(classify=lambda **kwargs: record(_INTENT))
    reranker = SimpleNamespace(rerank=lambda query, candidates, top_k: record(candidates[:top_k]))
    return embedder, classifier, reranker


@pytest.mark.parametrize("mode", ["dual", "single"])
async def test_embed_classify_and_rerank_never_run_on_the_loop_thread(monkeypatch, mode):
    from app.settings import settings

    monkeypatch.setattr(settings, "rerank_enabled", True)
    monkeypatch.setattr(settings, "retrieval_mode", mode)
    threads: set[int] = set()
    embedder, classifier, reranker = _recording(threads)
    lane = ThreadLane("t", 1)
    retriever = build_retriever(
        store=_Store(), embedder=embedder, classifier=classifier, reranker=reranker, compute=lane
    )

    await retriever.retrieve("q", tenant_id=DEFAULT_TENANT_ID, catalog=EMPTY_CATALOG)

    assert threads and threading.get_ident() not in threads
    lane.shutdown()


async def test_a_search_is_two_lane_calls_not_one_per_model(monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "rerank_enabled", True)
    lane = InlineLane()
    retriever = build_retriever(
        store=_Store(), classifier=SimpleNamespace(classify=lambda **kwargs: _INTENT), compute=lane
    )

    await retriever.retrieve("q", tenant_id=DEFAULT_TENANT_ID, catalog=EMPTY_CATALOG)

    assert lane.calls == 2


def test_warm_loads_every_query_path_model(monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "rerank_enabled", True)
    loaded: list[str] = []
    retriever = build_retriever(
        embedder=SimpleNamespace(embed_query=lambda text: loaded.append("embed") or [0.0]),
        classifier=SimpleNamespace(warm=lambda: loaded.append("centroids")),
        reranker=SimpleNamespace(rerank=lambda query, candidates, top_k: loaded.append("rerank") or candidates),
    )

    retriever.warm()

    assert loaded == ["embed", "centroids", "rerank"]


def test_one_failing_warm_up_step_does_not_stop_the_rest(monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "rerank_enabled", True)
    loaded: list[str] = []

    def broken(text):
        raise RuntimeError("model download failed")

    retriever = build_retriever(
        embedder=SimpleNamespace(embed_query=broken),
        classifier=SimpleNamespace(warm=lambda: loaded.append("centroids")),
        reranker=SimpleNamespace(rerank=lambda query, candidates, top_k: loaded.append("rerank") or candidates),
    )

    retriever.warm()

    assert loaded == ["centroids", "rerank"]
