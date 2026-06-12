from unittest.mock import AsyncMock

import pytest

from app.core.intent import QueryIntent
from app.core.query_analysis import QueryAnalysis
from app.core.retriever import RetrievalResult
from app.core.tools.mpmb_tools import Deps, _mpmb_search_impl


class FakeIntent:
    """Minimal stand-in exposing what the footer reads."""

    def __init__(self, intent: QueryIntent):
        self.primary = intent


def _chunk(source_file: str, content: str, score: float = 0.8, tier: str = "authoritative") -> dict:
    return {
        "content": content,
        "source_file": source_file,
        "edition": "2014",
        "source_tier": tier,
        "start_line": 10,
        "end_line": 42,
        "score": score,
    }


def _result(authoritative=None, examples=None, edition="2014") -> RetrievalResult:
    return RetrievalResult(
        authoritative=authoritative or [],
        examples=examples or [],
        intent=FakeIntent(QueryIntent.LOOKUP),
        query_analysis=QueryAnalysis(object_type=None, edition=edition),
        timing_ms=5.0,
    )


def _deps() -> Deps:
    return Deps(session_id="sess-1", edition="2014")


@pytest.mark.asyncio
async def test_search_formats_sections_citations_and_footer(monkeypatch):
    from app.core.retriever import retriever

    fake = _result(
        authoritative=[_chunk("_common/SpellsList.js", 'SpellsList["fireball"] = { name: "Fireball" };')],
        examples=[_chunk("examples/feat.js", "FeatsList['lucky'] = {};", score=0.61, tier="official_example")],
    )
    monkeypatch.setattr(retriever, "retrieve", AsyncMock(return_value=fake))

    out = await _mpmb_search_impl(_deps(), "how does fireball work")

    assert "## AUTHORITATIVE" in out
    assert "## EXAMPLES" in out
    assert "_common/SpellsList.js:10-42" in out
    assert "tier=authoritative" in out
    assert "score=0.80" in out
    assert 'SpellsList["fireball"]' in out
    assert "[retrieval: intent=lookup, edition=2014, chunks=2]" in out


@pytest.mark.asyncio
async def test_search_empty_result_is_not_an_error(monkeypatch):
    from app.core.retriever import retriever

    monkeypatch.setattr(retriever, "retrieve", AsyncMock(return_value=_result()))

    out = await _mpmb_search_impl(_deps(), "nonsense query", edition="2024")

    assert not out.startswith("[error]")
    assert "No indexed chunks matched" in out
    assert "nonsense query" in out
    assert "edition=2024" in out


@pytest.mark.asyncio
async def test_search_retriever_failure_returns_error_with_fallback_hint(monkeypatch):
    from app.core.retriever import retriever

    monkeypatch.setattr(retriever, "retrieve", AsyncMock(side_effect=RuntimeError("qdrant connection refused")))

    out = await _mpmb_search_impl(_deps(), "anything")

    assert out.startswith("[error] retrieval unavailable")
    assert "qdrant connection refused" in out
    assert "mpmb_grep" in out


@pytest.mark.asyncio
async def test_search_passes_query_and_edition_to_retriever(monkeypatch):
    from app.core.retriever import retriever

    fake_retrieve = AsyncMock(return_value=_result())
    monkeypatch.setattr(retriever, "retrieve", fake_retrieve)

    await _mpmb_search_impl(_deps(), "subclass syntax", edition="2024")

    fake_retrieve.assert_awaited_once()
    kwargs = fake_retrieve.await_args.kwargs
    assert kwargs["query"] == "subclass syntax"
    assert kwargs["edition"] == "2024"


@pytest.mark.asyncio
async def test_search_missing_intent_reports_unknown(monkeypatch):
    from app.core.retriever import retriever

    fake = _result(authoritative=[_chunk("a.js", "var x = 1;")])
    fake.intent = None
    monkeypatch.setattr(retriever, "retrieve", AsyncMock(return_value=fake))

    out = await _mpmb_search_impl(_deps(), "q")

    assert "intent=unknown" in out


def test_mpmb_search_registered_on_toolset():
    from app.core.tools import build_mpmb_toolset

    toolset = build_mpmb_toolset()
    assert "mpmb_search" in toolset.tools
    assert set(toolset.tools) == {"mpmb_search", "mpmb_read", "mpmb_grep", "mpmb_function"}
