from app.model.orm import Message, Session
from app.services.db import session_service
from app.services.db.connection import db
from app.services.db.session_service import _history_window
from app.settings import settings

OWNER = "history-owner"


def _msg(role: str, text: str) -> Message:
    return Message(role=role, content={"text": text})


def test_window_keeps_the_newest_turns_oldest_first():
    newest_first = [_msg("assistant", "a2"), _msg("user", "u2"), _msg("assistant", "a1"), _msg("user", "u1")]
    assert _history_window(newest_first, max_chars=100) == [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
    ]


def test_window_drops_the_oldest_turns_past_the_budget():
    newest_first = [
        _msg("assistant", "a" * 10),
        _msg("user", "u" * 10),
        _msg("assistant", "x" * 10),
        _msg("user", "y" * 10),
    ]
    assert [m["content"] for m in _history_window(newest_first, max_chars=25)] == ["u" * 10, "a" * 10]


def test_window_opens_on_a_user_turn():
    newest_first = [_msg("user", "u2"), _msg("assistant", "a1")]
    assert _history_window(newest_first, max_chars=100) == [{"role": "user", "content": "u2"}]


def test_window_skips_empty_and_system_messages():
    newest_first = [_msg("assistant", ""), _msg("system", "s"), _msg("user", "u1")]
    assert _history_window(newest_first, max_chars=100) == [{"role": "user", "content": "u1"}]


async def _seed(tenant_id: str, count: int):
    async with db.session() as s:
        row = Session(title="history", user_id=OWNER, tenant_id=tenant_id)
        s.add(row)
        await s.flush()
        for seq in range(1, count + 1):
            role = "user" if seq % 2 else "assistant"
            s.add(Message(session_id=row.id, role=role, content={"text": f"msg {seq}"}, sequence_number=seq))
        return row.id


async def test_history_sends_the_newest_messages(tenant_id, monkeypatch):
    monkeypatch.setattr(settings, "history_max_messages", 50)
    monkeypatch.setattr(settings, "history_max_chars", 100_000)
    session_id = await _seed(tenant_id, 60)

    history = await session_service.get_conversation_history(session_id, user_id=OWNER)

    assert len(history) == 50
    assert history[0] == {"role": "user", "content": "msg 11"}
    assert history[-1] == {"role": "assistant", "content": "msg 60"}
