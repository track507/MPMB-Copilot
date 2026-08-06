"""
Chat attachment linking

When a chat request carries attached_file_ids, the handler links them to the saved user message via upload_registry.link_message
The session-scoping of that link is the registry's job (covered in test_upload_registry)
here we assert the handler wires it up with the right message id, file ids, and session id
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def chat_client(monkeypatch):
    monkeypatch.setattr("app.api.chat.db", SimpleNamespace(is_connected=True))
    from app.main import app

    return TestClient(app)


def _wire_chat(monkeypatch, user_msg_id):
    """Mock enough of the chat pipeline that POST /chat returns 200."""

    async def fake_history(_session_uuid):
        return []

    async def fake_add_message(**_kwargs):
        # sequence_number != 1 avoids the async title-generation task
        return SimpleNamespace(id=user_msg_id, sequence_number=2)

    async def fake_generate(**_kwargs):
        return SimpleNamespace(
            content="ok", provider="p", model="m", usage={}, timing={}, tools=None, retrieval=None, stop_reason=None
        )

    monkeypatch.setattr("app.api.chat.session_service.get_conversation_history", fake_history)
    monkeypatch.setattr("app.api.chat.session_service.add_message", fake_add_message)
    monkeypatch.setattr("app.api.chat.rag_engine.generate", fake_generate)


def test_chat_links_attachments_to_the_user_message(chat_client, monkeypatch):
    sid, mid = uuid4(), uuid4()
    fid1, fid2 = uuid4(), uuid4()
    _wire_chat(monkeypatch, mid)
    link = AsyncMock(return_value=2)
    monkeypatch.setattr("app.api.chat.upload_registry.link_message", link)

    resp = chat_client.post(
        "/api/chat",
        json={"message": "hi", "session_id": str(sid), "attached_file_ids": [str(fid1), str(fid2)]},
    )

    assert resp.status_code == 200
    link.assert_awaited_once()
    kw = link.await_args.kwargs
    assert kw["message_id"] == mid
    assert kw["session_id"] == sid
    assert kw["file_ids"] == [fid1, fid2]


def test_chat_without_attachments_does_not_link(chat_client, monkeypatch):
    _wire_chat(monkeypatch, uuid4())
    link = AsyncMock()
    monkeypatch.setattr("app.api.chat.upload_registry.link_message", link)

    resp = chat_client.post("/api/chat", json={"message": "hi", "session_id": str(uuid4())})

    assert resp.status_code == 200
    link.assert_not_awaited()
