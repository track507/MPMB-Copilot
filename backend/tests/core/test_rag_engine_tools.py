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
    from app.core.query_analysis import QueryAnalysis
    from app.core.retriever import RetrievalResult
    from app.settings import settings

    mpmb = tmp_path / "mpmb_source"
    mpmb.mkdir()
    (mpmb / "X.js").write_text("var AbilityScores = { name: 'A' };\n")
    monkeypatch.setattr(config, "mpmb_source_dir", str(mpmb))
    monkeypatch.setattr(settings, "enable_tool_use", True)

    async def fake_retrieve(query: str, edition=None, intent_override=None):
        return RetrievalResult(
            authoritative=[],
            examples=[],
            intent=None,
            query_analysis=QueryAnalysis(object_type=None, edition=edition or "2014"),
            timing_ms=0.0,
        )

    monkeypatch.setattr("app.core.rag_engine.retriever.retrieve", fake_retrieve)

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
