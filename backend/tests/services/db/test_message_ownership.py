import pytest

from app.services.db import session_service

OWNER = "test-owner"


async def test_add_message_refuses_another_owner(session_id):
    with pytest.raises(LookupError):
        await session_service.add_message(session_id, "user", {"text": "planted"}, user_id="intruder")

    assert await session_service.delete_session(session_id, user_id=OWNER)


async def test_add_message_refuses_a_soft_deleted_session(session_id):
    assert await session_service.delete_session(session_id, user_id=OWNER)

    with pytest.raises(LookupError):
        await session_service.add_message(session_id, "user", {"text": "late"}, user_id=OWNER)

    assert await session_service.get_message_count(session_id) == 0


async def test_add_message_appends_for_the_owner(session_id):
    first = await session_service.add_message(session_id, "user", {"text": "a"}, user_id=OWNER)
    second = await session_service.add_message(session_id, "assistant", {"text": "b"}, user_id=OWNER)

    assert (first.sequence_number, second.sequence_number) == (1, 2)
