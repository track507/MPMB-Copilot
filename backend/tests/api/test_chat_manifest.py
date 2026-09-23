"""
The upload manifest is assembled at the edge, not inside the agent loop

Keeps app.core off the database: rag_engine receives the inventory as a string
"""

from uuid import uuid4

import pytest

import app.api.chat as chat_mod
from app.settings import settings


@pytest.fixture
def manifest_calls(monkeypatch):
    calls: list[dict] = []

    async def fake_build(*, session_id, user_id):
        calls.append({"session_id": session_id, "user_id": user_id})
        return "\n\n[uploaded files]\nlibrary: a.js (1)"

    monkeypatch.setattr(chat_mod, "build_upload_manifest", fake_build)
    return calls


async def test_the_edge_builds_the_manifest_for_the_caller(manifest_calls, monkeypatch):
    monkeypatch.setattr(settings, "enable_tool_use", True)
    session = uuid4()

    result = await chat_mod._upload_manifest(session, "u1")

    assert "[uploaded files]" in result
    assert manifest_calls == [{"session_id": session, "user_id": "u1"}]


async def test_no_manifest_and_no_query_when_tools_are_off(manifest_calls, monkeypatch):
    monkeypatch.setattr(settings, "enable_tool_use", False)

    assert await chat_mod._upload_manifest(uuid4(), "u1") == ""
    # ! Not merely blanked: the registry is never queried, so a disabled toolset costs no database round trip
    assert manifest_calls == []
