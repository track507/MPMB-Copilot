"""
The principal's user_id must reach the service on every session endpoint

tests/api/ never touches a real database - it monkeypatches the service layer (see tests/api/test_chat_persistence.py)
So this file proves the *wiring*: that thecaller's id is handed down, and that a miss renders as 404
The filtering itself is proven against a real Postgres in tests/services/db/test_session_ownership.py
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

ALICE = "11111111-1111-1111-1111-111111111111"
BOB = "22222222-2222-2222-2222-222222222222"


def _fake_session(user_id: str, title: str = "chat"):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        title=title,
        created_at=now,
        updated_at=now,
        user_id=user_id,
        settings={},
        meta_data={},
    )


@pytest.fixture
def as_user(monkeypatch):
    """Client factory authenticated as a chosen user, with the DB check satisfied."""
    from app.api import sessions as sessions_mod
    from app.api.deps import Principal, current_principal
    from app.main import app

    monkeypatch.setattr(sessions_mod, "db", SimpleNamespace(is_connected=True))

    def _client(user_id: str, role: str = "user") -> TestClient:
        app.dependency_overrides[current_principal] = lambda: Principal(user_id=user_id, role=role)
        return TestClient(app, raise_server_exceptions=False)

    yield _client
    app.dependency_overrides.pop(current_principal, None)


def test_create_passes_the_caller_as_owner(as_user, monkeypatch):
    from app.api import sessions as sessions_mod

    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _fake_session(kwargs["user_id"])

    monkeypatch.setattr(sessions_mod.session_service, "create_session", fake_create)

    response = as_user(ALICE).post("/api/sessions", json={"title": "Alice chat"})
    assert response.status_code == 201
    # ! The owner comes from the principal, never from the request body
    assert captured["user_id"] == ALICE


def test_list_and_count_are_scoped_to_the_caller(as_user, monkeypatch):
    from app.api import sessions as sessions_mod

    seen: dict = {}

    async def fake_list(*, user_id, limit, offset):
        seen["list"] = user_id
        return [_fake_session(user_id, "Bob chat")]

    async def fake_count(*, user_id):
        seen["count"] = user_id
        return 1

    async def fake_msg_count(session_id):
        return 0

    monkeypatch.setattr(sessions_mod.session_service, "list_sessions", fake_list)
    monkeypatch.setattr(sessions_mod.session_service, "get_session_count", fake_count)
    monkeypatch.setattr(sessions_mod.session_service, "get_message_count", fake_msg_count)

    body = as_user(BOB).get("/api/sessions").json()
    assert [s["title"] for s in body["sessions"]] == ["Bob chat"]
    assert seen["list"] == BOB
    # ? the total must be scoped too, or it leaks how many chats other tenants have
    assert seen["count"] == BOB


def test_another_owners_session_reads_as_404_not_403(as_user, monkeypatch):
    from app.api import sessions as sessions_mod

    async def not_found(*args, **kwargs):
        return None

    async def delete_missed(*args, **kwargs):
        return False

    monkeypatch.setattr(sessions_mod.session_service, "get_session_with_messages", not_found)
    monkeypatch.setattr(sessions_mod.session_service, "get_session", not_found)
    monkeypatch.setattr(sessions_mod.session_service, "update_session", not_found)
    monkeypatch.setattr(sessions_mod.session_service, "delete_session", delete_missed)

    bob = as_user(BOB)
    sid = uuid4()
    # ! 404, never 403: a 403 would confirm the session exists
    assert bob.get(f"/api/sessions/{sid}").status_code == 404
    assert bob.get(f"/api/sessions/{sid}/messages").status_code == 404
    assert bob.put(f"/api/sessions/{sid}", json={"title": "stolen"}).status_code == 404
    assert bob.delete(f"/api/sessions/{sid}").status_code == 404


def test_feedback_is_gated_on_session_ownership(as_user, monkeypatch):
    from app.api import sessions as sessions_mod

    async def not_found(*args, **kwargs):
        return None

    monkeypatch.setattr(sessions_mod.session_service, "get_session", not_found)

    sid, mid = uuid4(), uuid4()
    bob = as_user(BOB)
    assert bob.put(f"/api/sessions/{sid}/messages/{mid}/feedback", json={"rating": "up"}).status_code == 404
    assert bob.delete(f"/api/sessions/{sid}/messages/{mid}/feedback").status_code == 404


async def test_load_history_scopes_to_the_caller(monkeypatch):
    """A foreign session id must read as empty, not as someone else's turns."""
    from app.api import chat as chat_mod

    captured: dict = {}

    async def fake_history(session_id, *, user_id):
        captured["user_id"] = user_id
        return []

    monkeypatch.setattr(chat_mod.session_service, "get_conversation_history", fake_history)
    monkeypatch.setattr(chat_mod, "db", SimpleNamespace(is_connected=True))

    await chat_mod._load_history(str(uuid4()), BOB)
    # ! Scoped to the caller, not to the id they supplied
    assert captured["user_id"] == BOB


async def test_ensure_session_stamps_the_owner(monkeypatch):
    from app.api import chat as chat_mod

    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(chat_mod.session_service, "create_session", fake_create)
    monkeypatch.setattr(chat_mod, "db", SimpleNamespace(is_connected=True))

    await chat_mod._ensure_session(None, "2024", ALICE)
    assert captured["user_id"] == ALICE
