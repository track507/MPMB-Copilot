"""
The tenant boundary as the retriever sees it

Every assertion here is a negative: what a caller must NOT be able to reach, or to reach around
"""

import inspect
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.intent import IntentResult, QueryIntent
from app.core.storage_keys import SHARED_TENANT
from app.services.vector.qdrant import QdrantStore
from tests.core.builders import build_retriever

TENANT_A = "019f3400-0000-7000-8000-00000000000a"
TENANT_B = "019f3400-0000-7000-8000-00000000000b"

_CORPUS = [
    {"id": "a", "tenant_id": TENANT_A, "content": "tenant a note", "source_tier": "authoritative"},
    {"id": "b", "tenant_id": TENANT_B, "content": "tenant b note", "source_tier": "authoritative"},
    {"id": "s", "tenant_id": SHARED_TENANT, "content": "pack corpus", "source_tier": "authoritative"},
]


def _classifier():
    """A classifier returning a real IntentResult, so the retriever's budget and blending logic run unchanged"""
    result = IntentResult(
        primary=QueryIntent.LOOKUP,
        secondary=None,
        confidence=0.9,
        margin=0.5,
        is_blended=False,
        method="stub",
    )
    return SimpleNamespace(classify=lambda **kwargs: result)


class RecordingStore:
    """
    A store that applies the same visibility rule Qdrant would, and records what it was asked

    The point is to assert on the tenant the retriever passed down, not on Qdrant's wire format
    """

    def __init__(self) -> None:
        self.tenants_seen: list[str] = []

    async def hybrid_search(self, query_text, query_embedding, *, tenant_id, filters=None, **kwargs):
        self.tenants_seen.append(tenant_id)
        allowed = {tenant_id, SHARED_TENANT}
        return [dict(chunk) for chunk in _CORPUS if chunk["tenant_id"] in allowed]


async def test_a_search_never_returns_another_tenants_chunk():
    store = RecordingStore()
    retriever = build_retriever(store=store, classifier=_classifier())

    result = await retriever.retrieve(query="anything", tenant_id=TENANT_A)

    returned = {chunk["id"] for chunk in result.authoritative + result.examples}
    assert "b" not in returned


async def test_shared_pack_corpus_stays_readable():
    """Isolation must not cost the shared corpus, which every tenant is meant to read"""
    store = RecordingStore()
    retriever = build_retriever(store=store, classifier=_classifier())

    result = await retriever.retrieve(query="anything", tenant_id=TENANT_A)

    returned = {chunk["id"] for chunk in result.authoritative + result.examples}
    assert "s" in returned


async def test_every_store_call_carries_the_callers_tenant():
    """
    One retrieve can issue several searches, and each one must be scoped

    A single unscoped fallback query would leak just as completely as an unscoped primary one
    """
    store = RecordingStore()
    retriever = build_retriever(store=store, classifier=_classifier())

    await retriever.retrieve(query="anything", tenant_id=TENANT_A)

    assert store.tenants_seen
    assert set(store.tenants_seen) == {TENANT_A}


def test_retrieve_cannot_be_called_without_a_tenant():
    from app.core.retriever import Retriever

    param = inspect.signature(Retriever.retrieve).parameters["tenant_id"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty


def test_the_store_ports_also_require_a_tenant():
    """The same rule at the port, so an adapter cannot quietly make it optional"""
    for name in ("hybrid_search", "dense_search", "upsert_chunks"):
        param = inspect.signature(getattr(QdrantStore, name)).parameters["tenant_id"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY, name
        assert param.default is inspect.Parameter.empty, name


async def test_a_tool_argument_cannot_choose_the_tenant():
    """
    The tenant reaches the tools through Deps, never through a model-supplied argument

    A tool parameter named tenant would let the model pick whose content it reads
    """
    from app.core.tools import mpmb_tools

    source = inspect.getsource(mpmb_tools)
    assert "deps.tenant_id" in source
    assert "tenant_id=deps.tenant_id" in source


async def test_indexing_anything_but_pack_corpus_is_refused():
    """
    The index has no tenant dimension yet, so tenant content must fail loudly rather than land untagged

    An untagged chunk would be invisible to its owner and visible to nobody, or worse, shared
    """
    store = QdrantStore()

    with pytest.raises(RuntimeError, match="tenant-scoped"):
        await store.upsert_chunks([], [], tenant_id=TENANT_A)


@pytest.mark.parametrize("chunks", [[], [{"content": "x"}]])
async def test_the_refusal_happens_before_any_work(chunks: list[dict[str, Any]]):
    """It raises on an empty list too, so the guard is the first thing the method does"""
    store = QdrantStore()

    with pytest.raises(RuntimeError, match="tenant-scoped"):
        await store.upsert_chunks(chunks, [], tenant_id=TENANT_B)
