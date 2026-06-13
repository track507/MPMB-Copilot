import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from app.core.rag_engine import rag_engine
from app.core.tools import build_mpmb_toolset


@pytest.mark.asyncio
async def test_stream_emits_tool_events_when_model_calls_tool(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.config import config
    from app.settings import settings

    mpmb = tmp_path / "mpmb_source"
    mpmb.mkdir()
    (mpmb / "X.js").write_text("var AbilityScores = { name: 'A' };\n")
    monkeypatch.setattr(config, "mpmb_source_dir", str(mpmb))
    monkeypatch.setattr(settings, "enable_tool_use", True)

    call_counter = {"n": 0}

    async def fake_stream(messages: list[ModelMessage], info: AgentInfo):
        call_counter["n"] += 1
        if call_counter["n"] == 1:
            yield {
                0: DeltaToolCall(
                    name="mpmb_function",
                    json_args='{"root": "./data/mpmb_source/", "name": "AbilityScores"}',
                    tool_call_id="c1",
                )
            }
            return
        yield "Found it."

    def fake_build_agent(*args, **kwargs):
        toolset = kwargs.get("toolset") or build_mpmb_toolset()
        return Agent(
            FunctionModel(stream_function=fake_stream, model_name="test"),
            instructions="x",
            toolsets=[toolset],
        )

    monkeypatch.setattr("app.core.rag_engine.build_agent", fake_build_agent)

    events = []
    async for ev in rag_engine.stream(
        query="show AbilityScores",
        conversation_history=[],
        session_id="sess-1",
        edition="2014",
    ):
        events.append(ev)

    event_types = [e.event for e in events if e.event]
    assert "tool_start" in event_types
    assert "tool_end" in event_types
    final = events[-1]
    assert final.done
    assert final.tools is not None
    assert final.tools["total_calls"] >= 1
    assert final.tools["calls"][0]["name"] == "mpmb_function"
    assert final.tools["calls"][0]["status"] == "success"


def _setup_tool_stream_env(tmp_path, monkeypatch):
    """Shared scaffolding: temp source dir, tool use on, stubbed retriever.

    The retriever stub patches the singleton in `app.core.retriever` - the
    request path no longer touches it, only the mpmb_search tool does.
    Returns `(settings, fake_retrieve)` so tests can assert on retriever use.
    """
    from unittest.mock import AsyncMock

    from app.config import config
    from app.core.query_analysis import QueryAnalysis
    from app.core.retriever import RetrievalResult, retriever
    from app.settings import settings

    mpmb = tmp_path / "mpmb_source"
    mpmb.mkdir()
    (mpmb / "X.js").write_text("var AbilityScores = { name: 'A' };\n")
    monkeypatch.setattr(config, "mpmb_source_dir", str(mpmb))
    monkeypatch.setattr(settings, "enable_tool_use", True)

    fake_retrieve = AsyncMock(
        return_value=RetrievalResult(
            authoritative=[
                {
                    "source_file": "X.js",
                    "edition": "2014",
                    "source_tier": "authoritative",
                    "start_line": 1,
                    "end_line": 1,
                    "score": 0.9,
                    "content": "var AbilityScores = { name: 'A' };",
                }
            ],
            examples=[],
            intent=None,
            query_analysis=QueryAnalysis(object_type=None, edition="2014"),
            timing_ms=0.0,
        )
    )
    monkeypatch.setattr(retriever, "retrieve", fake_retrieve)
    return settings, fake_retrieve


def _fake_build_agent_factory(fake_stream):
    def fake_build_agent(*args, **kwargs):
        toolset = kwargs.get("toolset") or build_mpmb_toolset()
        return Agent(
            FunctionModel(stream_function=fake_stream, model_name="test"),
            instructions="x",
            toolsets=[toolset],
        )

    return fake_build_agent


@pytest.mark.asyncio
async def test_stream_soft_budget_lets_model_finish_answering(tmp_path, monkeypatch):
    """Over-budget tool calls get a stop notice; the model still answers normally."""
    settings, _ = _setup_tool_stream_env(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "max_tool_calls", 1)

    call_counter = {"n": 0}

    async def fake_stream(messages: list[ModelMessage], info: AgentInfo):
        call_counter["n"] += 1
        if call_counter["n"] <= 2:
            yield {
                0: DeltaToolCall(
                    name="mpmb_function",
                    json_args='{"root": "./data/mpmb_source/", "name": "AbilityScores"}',
                    tool_call_id=f"c{call_counter['n']}",
                )
            }
            return
        yield "Final answer after budget."

    monkeypatch.setattr("app.core.rag_engine.build_agent", _fake_build_agent_factory(fake_stream))

    events = []
    async for ev in rag_engine.stream(
        query="show AbilityScores",
        conversation_history=[],
        session_id="sess-1",
        edition="2014",
    ):
        events.append(ev)

    final = events[-1]
    assert final.done
    assert final.stop_reason != "tool_budget_exceeded"
    streamed_text = "".join(e.content for e in events if e.content)
    assert "Final answer after budget." in streamed_text
    assert final.tools is not None
    assert final.tools["total_calls"] == 2


@pytest.mark.asyncio
async def test_stream_hard_limit_degrades_gracefully(tmp_path, monkeypatch):
    """A model that never stops calling tools hits the hard net; the stream still
    ends with a done event and a notice instead of raising."""
    settings, _ = _setup_tool_stream_env(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "max_tool_calls", 2)

    call_counter = {"n": 0}

    async def fake_stream(messages: list[ModelMessage], info: AgentInfo):
        call_counter["n"] += 1
        yield {
            0: DeltaToolCall(
                name="mpmb_function",
                json_args='{"root": "./data/mpmb_source/", "name": "AbilityScores"}',
                tool_call_id=f"c{call_counter['n']}",
            )
        }

    monkeypatch.setattr("app.core.rag_engine.build_agent", _fake_build_agent_factory(fake_stream))

    events = []
    async for ev in rag_engine.stream(
        query="show AbilityScores",
        conversation_history=[],
        session_id="sess-1",
        edition="2014",
    ):
        events.append(ev)

    final = events[-1]
    assert final.done
    assert final.stop_reason == "tool_budget_exceeded"
    streamed_text = "".join(e.content for e in events if e.content)
    assert "tool-call limit" in streamed_text


@pytest.mark.asyncio
async def test_stream_does_not_pre_retrieve(tmp_path, monkeypatch):
    """The request path must not call the retriever; retrieval is agent-driven."""
    _, fake_retrieve = _setup_tool_stream_env(tmp_path, monkeypatch)

    async def fake_stream(messages: list[ModelMessage], info: AgentInfo):
        yield "Hello! How can I help with your MPMB sheet?"

    monkeypatch.setattr("app.core.rag_engine.build_agent", _fake_build_agent_factory(fake_stream))

    events = []
    async for ev in rag_engine.stream(
        query="Hi",
        conversation_history=[],
        session_id="sess-1",
        edition="2014",
    ):
        events.append(ev)

    fake_retrieve.assert_not_awaited()
    final = events[-1]
    assert final.done
    assert final.tools is None
    streamed_text = "".join(e.content for e in events if e.content)
    assert "Hello!" in streamed_text


@pytest.mark.asyncio
async def test_stream_mpmb_search_drives_retriever(tmp_path, monkeypatch):
    """When the model calls mpmb_search, the retriever runs and tool events flow."""
    _, fake_retrieve = _setup_tool_stream_env(tmp_path, monkeypatch)

    call_counter = {"n": 0}

    async def fake_stream(messages: list[ModelMessage], info: AgentInfo):
        call_counter["n"] += 1
        if call_counter["n"] == 1:
            yield {
                0: DeltaToolCall(
                    name="mpmb_search",
                    json_args='{"query": "how to add a race", "edition": "2014"}',
                    tool_call_id="s1",
                )
            }
            return
        yield "Here is how you add a race."

    monkeypatch.setattr("app.core.rag_engine.build_agent", _fake_build_agent_factory(fake_stream))

    events = []
    async for ev in rag_engine.stream(
        query="How do I make a 2014 race?",
        conversation_history=[],
        session_id="sess-1",
        edition="2014",
    ):
        events.append(ev)

    fake_retrieve.assert_awaited_once()
    assert fake_retrieve.await_args.kwargs["edition"] == "2014"
    final = events[-1]
    assert final.done
    assert final.tools is not None
    assert final.tools["calls"][0]["name"] == "mpmb_search"
    assert final.tools["calls"][0]["status"] == "success"
    streamed_text = "".join(e.content for e in events if e.content)
    assert "Here is how you add a race." in streamed_text
