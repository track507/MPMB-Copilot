from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.chunker import EDITION_UNKNOWN, detect_edition
from app.core.query_analysis import QueryAnalysis
from app.core.storage_keys import DEFAULT_TENANT_ID
from tests.core.builders import build_retriever


def _chunk(chunk_id: str, tier: str) -> dict:
    return {"id": chunk_id, "source_tier": tier, "content": "x", "source_file": "a.js"}


@pytest.mark.asyncio
async def test_dual_search_drops_object_type_from_authoritative_leg():
    """Authoritative chunks carry no object_type tag; filtering on it there
    guarantees zero results."""
    store = MagicMock()
    store.hybrid_search = AsyncMock(return_value=[_chunk("a1", "authoritative")])

    await build_retriever(store=store)._dual_search(
        query="RaceList attributes",
        query_embedding=[0.0] * 8,
        base_filters={"edition": "2024", "object_type": "RaceList"},
        budget={"authoritative": 3, "examples": 5},
        tenant_id=DEFAULT_TENANT_ID,
    )

    auth_call_filters = store.hybrid_search.await_args_list[0].kwargs["filters"]
    assert "object_type" not in auth_call_filters
    assert auth_call_filters["source_tier"] == "authoritative"
    ex_call_filters = store.hybrid_search.await_args_list[1].kwargs["filters"]
    assert ex_call_filters["object_type"] == "RaceList"


@pytest.mark.asyncio
async def test_dual_search_examples_fallback_drops_object_type_when_empty():
    """Thin object_type+edition combinations degrade to broader examples, not zero."""
    store = MagicMock()
    store.hybrid_search = AsyncMock(
        side_effect=[
            [],  # authoritative leg
            [],  # examples leg with object_type -> empty
            [_chunk("e1", "official_example")],  # relaxed retry
        ]
    )

    _, examples = await build_retriever(store=store)._dual_search(
        query="RaceList attributes",
        query_embedding=[0.0] * 8,
        base_filters={"edition": "2024", "object_type": "RaceList"},
        budget={"authoritative": 3, "examples": 5},
        tenant_id=DEFAULT_TENANT_ID,
    )

    assert len(examples) == 1
    assert store.hybrid_search.await_count == 3
    relaxed_filters = store.hybrid_search.await_args_list[2].kwargs["filters"]
    assert "object_type" not in relaxed_filters
    assert relaxed_filters["edition"] == "2024"


@pytest.mark.asyncio
async def test_dual_search_no_fallback_when_examples_found():
    store = MagicMock()
    store.hybrid_search = AsyncMock(
        side_effect=[
            [_chunk("a1", "authoritative")],
            [_chunk("e1", "official_example")],
        ]
    )

    auth, examples = await build_retriever(store=store)._dual_search(
        query="q",
        query_embedding=[0.0] * 8,
        base_filters={"edition": "2014", "object_type": "SpellsList"},
        budget={"authoritative": 3, "examples": 5},
        tenant_id=DEFAULT_TENANT_ID,
    )

    assert len(auth) == 1 and len(examples) == 1
    assert store.hybrid_search.await_count == 2


@pytest.mark.asyncio
async def test_single_search_fallback_drops_object_type_when_empty():
    store = MagicMock()
    store.hybrid_search = AsyncMock(
        side_effect=[
            [],  # filtered search -> empty
            [_chunk("a1", "authoritative"), _chunk("e1", "community_example")],
        ]
    )

    auth, examples = await build_retriever(store=store)._single_search(
        query="q",
        query_embedding=[0.0] * 8,
        base_filters={"edition": "2024", "object_type": "RaceList"},
        budget={"authoritative": 3, "examples": 5},
        tenant_id=DEFAULT_TENANT_ID,
    )

    assert len(auth) == 1 and len(examples) == 1
    relaxed_filters = store.hybrid_search.await_args_list[1].kwargs["filters"]
    assert "object_type" not in relaxed_filters


def test_edition_filter_admits_edition_agnostic_chunks():
    filters = build_retriever()._build_filters(QueryAnalysis(object_type=None, edition=None), "2014")
    assert filters["edition"] == ["2014", EDITION_UNKNOWN]


def test_engine_functions_carry_the_edition_the_filter_admits():
    edition = detect_edition("function GetFeatureChoice() {}", Path("_functions/Functions1.js"), {})
    assert edition == EDITION_UNKNOWN


def test_no_edition_means_no_edition_filter():
    filters = build_retriever()._build_filters(QueryAnalysis(object_type=None, edition=None), None)
    assert "edition" not in filters
