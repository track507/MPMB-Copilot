from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.storage_keys import DEFAULT_TENANT_ID

ALICE = "11111111-1111-1111-1111-111111111111"
BOB = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def wired(monkeypatch):
    from app.api import chat as chat_mod
    from app.api.deps import Principal, current_principal
    from app.main import app

    owners: dict = {}
    added: list[dict] = []

    async def fake_get_session(session_id, *, user_id):
        return SimpleNamespace(id=session_id) if owners.get(session_id) == user_id else None

    async def fake_history(session_id, *, user_id):
        return []

    async def fake_add_message(**kwargs):
        added.append(kwargs)
        return SimpleNamespace(id=uuid4(), sequence_number=2)

    async def generate(**_kwargs):
        return SimpleNamespace(
            content="ok", provider="p", model="m", usage={}, timing={}, tools=None, retrieval=None, stop_reason=None
        )

    async def stream(**_kwargs):
        yield SimpleNamespace(done=False, event=None, content="ok")

    monkeypatch.setattr(chat_mod, "db", SimpleNamespace(is_connected=True))
    monkeypatch.setattr(chat_mod.session_service, "get_session", fake_get_session)
    monkeypatch.setattr(chat_mod.session_service, "get_conversation_history", fake_history)
    monkeypatch.setattr(chat_mod.session_service, "add_message", fake_add_message)
    monkeypatch.setattr(chat_mod, "get_rag_engine", lambda: SimpleNamespace(generate=generate, stream=stream))

    def client_for(user_id: str) -> TestClient:
        app.dependency_overrides[current_principal] = lambda: Principal(
            user_id=user_id, role="user", tenant_id=DEFAULT_TENANT_ID
        )
        return TestClient(app, raise_server_exceptions=False)

    yield SimpleNamespace(owners=owners, added=added, client_for=client_for)
    app.dependency_overrides.pop(current_principal, None)


@pytest.mark.parametrize("path", ["/api/chat", "/api/chat/stream"])
def test_a_session_the_caller_does_not_own_is_a_404_and_nothing_is_written(wired, path):
    sid = uuid4()
    wired.owners[sid] = ALICE

    response = wired.client_for(BOB).post(path, json={"message": "planted", "session_id": str(sid)})

    assert response.status_code == 404
    assert wired.added == []


def test_the_owner_continues_their_own_session(wired):
    sid = uuid4()
    wired.owners[sid] = ALICE

    response = wired.client_for(ALICE).post("/api/chat", json={"message": "hi", "session_id": str(sid)})

    assert response.status_code == 200
    assert response.json()["session_id"] == str(sid)
    assert [m["session_id"] for m in wired.added] == [sid, sid]
    assert {m["user_id"] for m in wired.added} == {ALICE}


@pytest.mark.parametrize("session_id", ["../../../..", "not-a-uuid", ""])
def test_a_malformed_session_id_is_rejected_before_any_handler_code(wired, session_id):
    response = wired.client_for(ALICE).post("/api/chat", json={"message": "hi", "session_id": session_id})

    assert response.status_code == 422
    assert wired.added == []


@pytest.mark.parametrize("edition", ["2024\u0000", "5e", "../2014"])
def test_an_edition_outside_the_known_set_is_rejected(wired, edition):
    response = wired.client_for(ALICE).post("/api/chat", json={"message": "hi", "edition": edition})

    assert response.status_code == 422
    assert wired.added == []
