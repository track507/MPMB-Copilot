from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.retriever import Retriever


def _chunk(chunk_id: str, tier: str) -> dict:
    return {"id": chunk_id, "source_tier": tier, "content": "x", "source_file": "a.js"}


@pytest.mark.asyncio
async def test_dual_search_drops_object_type_from_authoritative_leg(monkeypatch):
    """Authoritative chunks carry no object_type tag; filtering on it there
    guarantees zero results."""
    store = MagicMock()
    store.hybrid_search = AsyncMock(return_value=[_chunk("a1", "authoritative")])
    monkeypatch.setattr("app.core.retriever.get_vector_store", lambda: store)

    await Retriever()._dual_search(
        query="RaceList attributes",
        query_embedding=[0.0] * 8,
        base_filters={"edition": "2024", "object_type": "RaceList"},
        budget={"authoritative": 3, "examples": 5},
    )

    auth_call_filters = store.hybrid_search.await_args_list[0].kwargs["filters"]
    assert "object_type" not in auth_call_filters
    assert auth_call_filters["source_tier"] == "authoritative"
    ex_call_filters = store.hybrid_search.await_args_list[1].kwargs["filters"]
    assert ex_call_filters["object_type"] == "RaceList"


@pytest.mark.asyncio
async def test_dual_search_examples_fallback_drops_object_type_when_empty(monkeypatch):
    """Thin object_type+edition combinations degrade to broader examples, not zero."""
    store = MagicMock()
    store.hybrid_search = AsyncMock(
        side_effect=[
            [],  # authoritative leg
            [],  # examples leg with object_type -> empty
            [_chunk("e1", "official_example")],  # relaxed retry
        ]
    )
    monkeypatch.setattr("app.core.retriever.get_vector_store", lambda: store)

    _, examples = await Retriever()._dual_search(
        query="RaceList attributes",
        query_embedding=[0.0] * 8,
        base_filters={"edition": "2024", "object_type": "RaceList"},
        budget={"authoritative": 3, "examples": 5},
    )

    assert len(examples) == 1
    assert store.hybrid_search.await_count == 3
    relaxed_filters = store.hybrid_search.await_args_list[2].kwargs["filters"]
    assert "object_type" not in relaxed_filters
    assert relaxed_filters["edition"] == "2024"


@pytest.mark.asyncio
async def test_dual_search_no_fallback_when_examples_found(monkeypatch):
    store = MagicMock()
    store.hybrid_search = AsyncMock(
        side_effect=[
            [_chunk("a1", "authoritative")],
            [_chunk("e1", "official_example")],
        ]
    )
    monkeypatch.setattr("app.core.retriever.get_vector_store", lambda: store)

    auth, examples = await Retriever()._dual_search(
        query="q",
        query_embedding=[0.0] * 8,
        base_filters={"edition": "2014", "object_type": "SpellsList"},
        budget={"authoritative": 3, "examples": 5},
    )

    assert len(auth) == 1 and len(examples) == 1
    assert store.hybrid_search.await_count == 2


@pytest.mark.asyncio
async def test_single_search_fallback_drops_object_type_when_empty(monkeypatch):
    store = MagicMock()
    store.hybrid_search = AsyncMock(
        side_effect=[
            [],  # filtered search -> empty
            [_chunk("a1", "authoritative"), _chunk("e1", "community_example")],
        ]
    )
    monkeypatch.setattr("app.core.retriever.get_vector_store", lambda: store)

    auth, examples = await Retriever()._single_search(
        query="q",
        query_embedding=[0.0] * 8,
        base_filters={"edition": "2024", "object_type": "RaceList"},
        budget={"authoritative": 3, "examples": 5},
    )

    assert len(auth) == 1 and len(examples) == 1
    relaxed_filters = store.hybrid_search.await_args_list[1].kwargs["filters"]
    assert "object_type" not in relaxed_filters
