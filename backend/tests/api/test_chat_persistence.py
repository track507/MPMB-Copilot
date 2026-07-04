from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import chat as chat_mod


def test_build_metadata_includes_retrieval_group():
    trace = [{"tool": "mpmb_search", "query": "q", "edition": "2014", "chunks": []}]
    meta = chat_mod._build_metadata(session_id="s", retrieval=trace)
    assert meta["retrieval"] == trace


def test_build_metadata_omits_retrieval_when_absent():
    assert "retrieval" not in chat_mod._build_metadata(session_id="s")


@pytest.mark.asyncio
async def test_save_assistant_message_persists_retrieval(monkeypatch):
    captured: dict = {}

    async def fake_add_message(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(sequence_number=2)

    monkeypatch.setattr(chat_mod.session_service, "add_message", fake_add_message)
    monkeypatch.setattr(chat_mod, "db", SimpleNamespace(is_connected=True))

    trace = [{"tool": "mpmb_search", "query": "q", "edition": "2014", "chunks": []}]
    rag_response = SimpleNamespace(
        content="answer",
        provider="anthropic",
        model="m",
        usage={},
        timing={},
        tools=None,
        stop_reason=None,
        retrieval=trace,
    )
    await chat_mod._save_assistant_message(uuid4(), "answer", rag_response)

    assert captured["meta_data"]["retrieval"] == trace
