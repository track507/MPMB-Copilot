from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    # Endpoints gate on db.is_connected; pretend the DB is up
    monkeypatch.setattr("app.api.sessions.db", SimpleNamespace(is_connected=True))
    from app.main import app

    return TestClient(app)


def _assistant_message(session_id, message_id):
    async def fake_get_message(_id):
        return SimpleNamespace(id=message_id, session_id=session_id, role="assistant")

    return fake_get_message


def test_set_feedback_on_assistant_message(client, monkeypatch):
    sid, mid = uuid4(), uuid4()
    now = datetime.now(timezone.utc)

    async def fake_set_feedback(_mid, rating, note):
        return SimpleNamespace(rating=rating, note=note, created_at=now, updated_at=now)

    monkeypatch.setattr("app.api.sessions.feedback_service.get_message", _assistant_message(sid, mid))
    monkeypatch.setattr("app.api.sessions.feedback_service.set_feedback", fake_set_feedback)

    resp = client.put(f"/api/sessions/{sid}/messages/{mid}/feedback", json={"rating": "down", "note": "wrong edition"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rating"] == "down"
    assert body["note"] == "wrong edition"


def test_invalid_rating_is_rejected(client, monkeypatch):
    sid, mid = uuid4(), uuid4()
    monkeypatch.setattr("app.api.sessions.feedback_service.get_message", _assistant_message(sid, mid))
    resp = client.put(f"/api/sessions/{sid}/messages/{mid}/feedback", json={"rating": "meh"})
    assert resp.status_code == 422


def test_note_too_long_is_rejected(client, monkeypatch):
    sid, mid = uuid4(), uuid4()
    monkeypatch.setattr("app.api.sessions.feedback_service.get_message", _assistant_message(sid, mid))
    resp = client.put(
        f"/api/sessions/{sid}/messages/{mid}/feedback",
        json={"rating": "up", "note": "x" * 2001},
    )
    assert resp.status_code == 422


def test_missing_message_is_404(client, monkeypatch):
    sid, mid = uuid4(), uuid4()

    async def fake_get_message(_id):
        return None

    monkeypatch.setattr("app.api.sessions.feedback_service.get_message", fake_get_message)
    resp = client.put(f"/api/sessions/{sid}/messages/{mid}/feedback", json={"rating": "up"})
    assert resp.status_code == 404


def test_feedback_on_user_message_is_400(client, monkeypatch):
    sid, mid = uuid4(), uuid4()

    async def fake_get_message(_id):
        return SimpleNamespace(id=mid, session_id=sid, role="user")

    monkeypatch.setattr("app.api.sessions.feedback_service.get_message", fake_get_message)
    resp = client.put(f"/api/sessions/{sid}/messages/{mid}/feedback", json={"rating": "up"})
    assert resp.status_code == 400


def test_clear_feedback_returns_204(client, monkeypatch):
    sid, mid = uuid4(), uuid4()

    async def fake_clear(_mid):
        return True

    monkeypatch.setattr("app.api.sessions.feedback_service.clear_feedback", fake_clear)
    resp = client.delete(f"/api/sessions/{sid}/messages/{mid}/feedback")
    assert resp.status_code == 204
