import asyncio
import gc
from types import SimpleNamespace
from uuid import uuid4

import anyio
import pytest
from fastapi.testclient import TestClient

from app.api import chat as chat_mod
from app.api.admission import TurnGate, turn_gate
from app.api.deps import Principal
from app.api.problem import ProblemError
from app.core.storage_keys import DEFAULT_TENANT_ID
from app.model.schemas.chat import ChatRequest
from app.settings import settings

USER_A = "user-a"
USER_B = "user-b"


@pytest.fixture
def caps(monkeypatch):
    def set_caps(total: int, per_user: int) -> None:
        monkeypatch.setattr(settings, "max_concurrent_turns", total)
        monkeypatch.setattr(settings, "max_concurrent_turns_per_user", per_user)

    return set_caps


def test_a_user_at_their_cap_is_refused_with_a_429_while_another_user_is_admitted(caps):
    caps(total=10, per_user=1)
    gate = TurnGate()
    gate.acquire(USER_A)

    with pytest.raises(ProblemError) as refused:
        gate.acquire(USER_A)
    gate.acquire(USER_B)

    assert refused.value.status == 429
    assert refused.value.headers == {"Retry-After": "5"}


def test_the_process_cap_sheds_with_a_503(caps):
    caps(total=1, per_user=5)
    gate = TurnGate()
    gate.acquire(USER_A)

    with pytest.raises(ProblemError) as refused:
        gate.acquire(USER_B)

    assert refused.value.status == 503
    assert refused.value.type == "/api/problems/server-busy"


def test_many_users_run_at_once_up_to_the_process_cap(caps):
    caps(total=100, per_user=1)
    gate = TurnGate()

    for i in range(100):
        gate.acquire(f"user-{i}")

    with pytest.raises(ProblemError):
        gate.acquire("user-100")


def test_releasing_twice_frees_one_slot(caps):
    caps(total=10, per_user=2)
    gate = TurnGate()
    slot = gate.acquire(USER_A)
    gate.acquire(USER_A)

    slot.release()
    slot.release()

    assert gate.active(USER_A) == 1


def test_a_settings_change_applies_to_the_next_acquire(caps):
    caps(total=10, per_user=1)
    gate = TurnGate()
    gate.acquire(USER_A)

    caps(total=10, per_user=2)

    gate.acquire(USER_A)


@pytest.fixture
def chat_client(monkeypatch):
    monkeypatch.setattr("app.api.chat.db", SimpleNamespace(is_connected=True))
    from app.main import app

    return TestClient(app)


@pytest.fixture
def saved(monkeypatch) -> list[dict]:
    messages: list[dict] = []

    async def fake_history(_session_uuid, *, user_id):
        return []

    async def fake_add_message(**kwargs):
        messages.append(kwargs)
        return SimpleNamespace(id=uuid4(), sequence_number=2)

    monkeypatch.setattr("app.api.chat.db", SimpleNamespace(is_connected=True))
    monkeypatch.setattr("app.api.chat.session_service.get_conversation_history", fake_history)
    monkeypatch.setattr("app.api.chat.session_service.add_message", fake_add_message)
    return messages


def _engine(monkeypatch, *, generate=None, stream=None) -> None:
    monkeypatch.setattr("app.api.chat.get_rag_engine", lambda: SimpleNamespace(generate=generate, stream=stream))


def _assistant(saved: list[dict]) -> list[dict]:
    return [m for m in saved if m.get("role") == "assistant"]


def test_a_refused_turn_carries_retry_after_and_persists_nothing(chat_client, saved, caps):
    caps(total=0, per_user=0)

    resp = chat_client.post("/api/chat", json={"message": "hi", "session_id": str(uuid4())})

    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "5"
    assert saved == []


def test_a_completed_turn_releases_its_slot(chat_client, saved, monkeypatch):
    async def generate(**_kwargs):
        return SimpleNamespace(
            content="ok", provider="p", model="m", usage={}, timing={}, tools=None, retrieval=None, stop_reason=None
        )

    _engine(monkeypatch, generate=generate)

    assert chat_client.post("/api/chat", json={"message": "hi", "session_id": str(uuid4())}).status_code == 200
    assert turn_gate.active() == 0


def test_a_non_stream_turn_past_its_deadline_is_a_504(chat_client, saved, monkeypatch):
    monkeypatch.setattr(settings, "turn_timeout_sec", 0.05)

    async def generate(**_kwargs):
        await asyncio.sleep(30)

    _engine(monkeypatch, generate=generate)

    resp = chat_client.post("/api/chat", json={"message": "hi", "session_id": str(uuid4())})

    assert resp.status_code == 504
    assert "exceeded its 0.05s limit" in resp.json()["detail"]
    assert turn_gate.active() == 0


def test_a_hung_turn_is_ended_by_the_deadline_and_saved_with_an_error(chat_client, saved, monkeypatch):
    monkeypatch.setattr(settings, "turn_timeout_sec", 0.1)

    async def stream(**_kwargs):
        yield SimpleNamespace(done=False, event=None, content="partial ")
        await asyncio.sleep(30)

    _engine(monkeypatch, stream=stream)

    resp = chat_client.post("/api/chat/stream", json={"message": "hi", "session_id": str(uuid4())})

    assert resp.status_code == 200
    assistant = _assistant(saved)
    assert len(assistant) == 1
    assert assistant[0]["content"] == {"text": "partial "}
    assert "exceeded its 0.1s limit" in assistant[0]["meta_data"]["error"]
    assert turn_gate.active() == 0


def test_a_stream_that_fails_after_its_answer_was_saved_is_not_saved_twice(chat_client, saved, monkeypatch):
    async def stream(**_kwargs):
        yield SimpleNamespace(
            done=True,
            event=None,
            content="",
            provider="p",
            model="m",
            usage={},
            timing={},
            tools=None,
            stop_reason=None,
            retrieval=None,
        )
        raise RuntimeError("late failure")

    _engine(monkeypatch, stream=stream)

    chat_client.post("/api/chat/stream", json={"message": "hi", "session_id": str(uuid4())})

    assert len(_assistant(saved)) == 1


async def _stream_response(monkeypatch, caps, agent):
    caps(total=10, per_user=5)
    _engine(monkeypatch, stream=agent)
    request = ChatRequest(message="hi", session_id=str(uuid4()))
    principal = Principal(user_id="stream-user", role="admin", tenant_id=DEFAULT_TENANT_ID)
    return await chat_mod.chat_stream(request, principal)


async def test_a_finished_stream_releases_its_slot_while_still_referenced(saved, monkeypatch, caps):
    async def agent(**_kwargs):
        yield SimpleNamespace(done=False, event=None, content="hello")

    response = await _stream_response(monkeypatch, caps, agent)
    body = response.body_iterator
    async for _ in body:
        pass

    assert turn_gate.active("stream-user") == 0


async def test_a_stream_that_never_starts_releases_its_slot_when_collected(saved, monkeypatch, caps):
    async def agent(**_kwargs):
        yield SimpleNamespace(done=False, event=None, content="never read")

    response = await _stream_response(monkeypatch, caps, agent)
    assert turn_gate.active("stream-user") == 1

    del response
    gc.collect()

    assert turn_gate.active("stream-user") == 0


async def test_a_cancelled_stream_saves_its_partial_answer(saved, monkeypatch, caps):
    async def agent(**_kwargs):
        yield SimpleNamespace(done=False, event=None, content="half an ")
        await asyncio.sleep(30)

    response = await _stream_response(monkeypatch, caps, agent)
    body = response.body_iterator

    async def consume() -> None:
        async for _ in body:
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assistant = _assistant(saved)
    assert assistant[0]["content"] == {"text": "half an "}
    assert assistant[0]["meta_data"]["error"] == "interrupted before the answer finished"
    assert turn_gate.active("stream-user") == 0


async def test_a_save_completes_inside_a_scope_that_is_already_cancelled(monkeypatch):
    committed: list[str] = []

    async def slow_save(session_uuid, text, rag_response=None, error=None):
        await asyncio.sleep(0.01)
        committed.append(text)

    monkeypatch.setattr(chat_mod, "_save_assistant_message", slow_save)

    with anyio.CancelScope() as scope:
        scope.cancel()
        await chat_mod._persist(None, "partial", error="interrupted")

    assert committed == ["partial"]


async def test_the_deadline_closes_the_agent_stream_it_abandons(monkeypatch):
    monkeypatch.setattr(settings, "turn_timeout_sec", 0.05)
    closed = False

    async def agent():
        nonlocal closed
        try:
            yield "first"
            await asyncio.sleep(30)
        finally:
            closed = True

    seen: list[str] = []
    with pytest.raises(TimeoutError, match="exceeded"):
        async for event in chat_mod._bounded(agent()):
            seen.append(event)

    assert seen == ["first"]
    assert closed


async def test_a_timeout_from_inside_the_turn_keeps_its_own_message(monkeypatch):
    monkeypatch.setattr(settings, "turn_timeout_sec", 30)

    async def work():
        raise TimeoutError("database pool exhausted")

    with pytest.raises(TimeoutError, match="database pool exhausted"):
        await chat_mod._within_deadline(work())


def test_zero_caps_are_rejected_by_the_settings_api():
    from pydantic import ValidationError

    from app.api.settings import SettingsUpdate

    for field in ("max_concurrent_turns", "max_concurrent_turns_per_user", "turn_timeout_sec"):
        with pytest.raises(ValidationError):
            SettingsUpdate(**{field: 0})
