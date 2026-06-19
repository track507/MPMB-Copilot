from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.retriever import Retriever


def _chunk(chunk_id: str, tier: str) -> dict:
    return {"id": chunk_id, "source_tier": tier, "content": chunk_id, "source_file": "a.js"}


@pytest.mark.asyncio
async def test_dual_reranks_each_tier_to_budget_when_enabled(monkeypatch):
    from app.core import retriever as rmod
    from app.settings import settings

    # Wide pools: 5 candidates per tier
    auth_pool = [_chunk(f"a{i}", "authoritative") for i in range(5)]
    ex_pool = [_chunk(f"e{i}", "official_example") for i in range(5)]
    store = MagicMock()
    store.hybrid_search = AsyncMock(side_effect=[auth_pool, ex_pool])
    monkeypatch.setattr("app.core.retriever.get_vector_store", lambda: store)

    monkeypatch.setattr(settings, "rerank_enabled", True)
    monkeypatch.setattr(settings, "rerank_candidate_k", 5)

    # Deterministic reranker: reverse order, cut to top_k
    fake = MagicMock()
    fake.rerank = lambda query, candidates, top_k: list(reversed(candidates))[:top_k]
    monkeypatch.setattr(rmod, "rerank_service", fake)

    auth, examples = await Retriever()._dual_search(
        query="q",
        query_embedding=[0.0] * 8,
        base_filters={"edition": "2014"},
        budget={"authoritative": 3, "examples": 2},
    )

    # Cut to budget, order reversed by the fake reranker
    assert [c["id"] for c in auth] == ["a4", "a3", "a2"]
    assert [c["id"] for c in examples] == ["e4", "e3"]
    # Pool was widened to candidate_k and prefetch lifted to match
    first_call = store.hybrid_search.await_args_list[0].kwargs
    assert first_call["limit"] == 5
    assert first_call["dense_limit"] == 20 and first_call["sparse_limit"] == 20  # max(20, 5)


@pytest.mark.asyncio
async def test_dual_disabled_path_is_unchanged(monkeypatch):
    from app.core import retriever as rmod
    from app.settings import settings

    store = MagicMock()
    store.hybrid_search = AsyncMock(side_effect=[[_chunk("a1", "authoritative")], [_chunk("e1", "official_example")]])
    monkeypatch.setattr("app.core.retriever.get_vector_store", lambda: store)
    monkeypatch.setattr(settings, "rerank_enabled", False)

    fake = MagicMock()
    monkeypatch.setattr(rmod, "rerank_service", fake)

    await Retriever()._dual_search(
        query="q",
        query_embedding=[0.0] * 8,
        base_filters={"edition": "2014"},
        budget={"authoritative": 3, "examples": 5},
    )

    # Disabled: budget passed straight to hybrid_search, reranker never called
    assert store.hybrid_search.await_args_list[0].kwargs["limit"] == 3
    fake.rerank.assert_not_called()


@pytest.mark.asyncio
async def test_single_reranks_each_tier_split_when_enabled(monkeypatch):
    from app.core import retriever as rmod
    from app.settings import settings

    pool = [_chunk(f"a{i}", "authoritative") for i in range(4)] + [
        _chunk(f"e{i}", "community_example") for i in range(4)
    ]
    store = MagicMock()
    store.hybrid_search = AsyncMock(side_effect=[pool])
    monkeypatch.setattr("app.core.retriever.get_vector_store", lambda: store)

    monkeypatch.setattr(settings, "rerank_enabled", True)
    monkeypatch.setattr(settings, "rerank_candidate_k", 8)

    fake = MagicMock()
    fake.rerank = lambda query, candidates, top_k: list(reversed(candidates))[:top_k]
    monkeypatch.setattr(rmod, "rerank_service", fake)

    auth, examples = await Retriever()._single_search(
        query="q",
        query_embedding=[0.0] * 8,
        base_filters={"edition": "2014"},
        budget={"authoritative": 2, "examples": 2},
    )

    # Each tier split reranked (reversed) and cut to its budget
    assert [c["id"] for c in auth] == ["a3", "a2"]
    assert [c["id"] for c in examples] == ["e3", "e2"]
