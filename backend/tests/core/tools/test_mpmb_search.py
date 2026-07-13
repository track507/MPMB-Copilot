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


def _chunk(
    source_file: str, content: str, score: float = 0.8, tier: str = "authoritative", object_type: str | None = None
) -> dict:
    chunk = {
        "content": content,
        "source_file": source_file,
        "edition": "2014",
        "source_tier": tier,
        "start_line": 10,
        "end_line": 42,
        "score": score,
    }
    if object_type is not None:
        chunk["metadata"] = {"object_type": object_type}
    return chunk


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


@pytest.mark.asyncio
async def test_search_flags_repeated_overlapping_results(monkeypatch):
    """A second search that mostly returns already-seen chunks gets a stop nudge."""
    from app.core.retriever import retriever

    chunks = [_chunk("a.js", "x"), _chunk("b.js", "y")]
    monkeypatch.setattr(retriever, "retrieve", AsyncMock(return_value=_result(authoritative=chunks)))

    deps = _deps()
    first = await _mpmb_search_impl(deps, "spell list class")
    assert "[note]" not in first

    second = await _mpmb_search_impl(deps, "class spell list variations")
    assert "[note]" in second
    assert "repeat earlier searches" in second


@pytest.mark.asyncio
async def test_search_no_nudge_for_fresh_results(monkeypatch):
    """Distinct results on the second search do not trigger the nudge."""
    from app.core.retriever import retriever

    fake = AsyncMock(
        side_effect=[_result(authoritative=[_chunk("a.js", "x")]), _result(authoritative=[_chunk("c.js", "z")])]
    )
    monkeypatch.setattr(retriever, "retrieve", fake)

    deps = _deps()
    await _mpmb_search_impl(deps, "first")
    second = await _mpmb_search_impl(deps, "second")
    assert "[note]" not in second


def test_mpmb_search_registered_on_toolset():
    from app.core.tools import build_mpmb_toolset

    toolset = build_mpmb_toolset()
    assert "mpmb_search" in toolset.tools
    assert set(toolset.tools) == {"mpmb_search", "mpmb_read", "mpmb_grep", "mpmb_function"}


@pytest.mark.asyncio
async def test_search_records_citation_trace_on_deps(monkeypatch):
    from app.core.retriever import retriever

    fake = _result(
        authoritative=[_chunk("_common/SpellsList.js", 'SpellsList["fireball"] = {};', object_type="SpellsList")],
        examples=[_chunk("examples/feat.js", "FeatsList['lucky'] = {};", score=0.61, tier="official_example")],
    )
    monkeypatch.setattr(retriever, "retrieve", AsyncMock(return_value=fake))

    deps = _deps()
    await _mpmb_search_impl(deps, "how does fireball work")

    assert len(deps.trace) == 1
    entry = deps.trace[0]
    assert entry["tool"] == "mpmb_search"
    assert entry["query"] == "how does fireball work"
    assert len(entry["chunks"]) == 2
    chunk = entry["chunks"][0]
    assert chunk["source_file"] == "_common/SpellsList.js"
    assert chunk["start_line"] == 10 and chunk["end_line"] == 42
    assert chunk["tier"] == "authoritative"
    assert chunk["score"] == 0.8
    # ? Trace carries object_type so the feedback exporter can auto-fill expect
    assert chunk["object_type"] == "SpellsList"
    assert entry["chunks"][1]["object_type"] is None
    # ! citation only - never the chunk body
    assert "content" not in chunk


@pytest.mark.asyncio
async def test_search_records_empty_trace_entry(monkeypatch):
    from app.core.retriever import retriever

    monkeypatch.setattr(retriever, "retrieve", AsyncMock(return_value=_result()))

    deps = _deps()
    await _mpmb_search_impl(deps, "nonsense", edition="2024")

    assert len(deps.trace) == 1
    assert deps.trace[0]["chunks"] == []
    assert deps.trace[0]["query"] == "nonsense"
