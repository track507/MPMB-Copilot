"""
Upload-registry DB ops - integration tests against a real Postgres

Fixtures (db_session_scope / session_id / message_id) live in the package conftest; each test starts from a truncated schema
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.db import session_service, upload_registry


async def _upsert(
    *,
    scope: str = "global",
    filename: str = "a.js",
    owner: str = "u1",
    session_id=None,
    file_hash: str = "h1",
    file_size: int = 10,
):
    """
    Upsert a file with sensible defaults; override only what a test cares about
    """
    return await upload_registry.upsert_file(
        scope=scope,
        filename=filename,
        original_filename=filename,
        file_path=f"{scope}/{filename}",
        content_type="text/javascript",
        file_size=file_size,
        file_hash=file_hash,
        owner_user_id=owner,
        session_id=session_id,
    )


# * upsert: same name in a scope updates one row in place


async def test_upsert_same_session_name_updates_in_place(session_id: UUID):
    a = await upload_registry.upsert_file(
        scope="session",
        filename="a.js",
        original_filename="a.js",
        file_path=f"session/{session_id}/a.js",
        content_type="text/javascript",
        file_size=10,
        file_hash="h1",
        owner_user_id="u1",
        session_id=session_id,
    )
    b = await upload_registry.upsert_file(
        scope="session",
        filename="a.js",
        original_filename="a.js",
        file_path=f"session/{session_id}/a.js",
        content_type="text/javascript",
        file_size=20,
        file_hash="h2",
        owner_user_id="u1",
        session_id=session_id,
    )
    assert a.id == b.id  # same row, upsert not insert
    assert b.file_hash == "h2"  # content replaced
    assert await upload_registry.count_files(scope="session", session_id=session_id) == 1


async def test_upsert_same_global_name_updates_in_place(db_session_scope):
    a = await _upsert(scope="global", owner="u1", file_hash="h1")
    b = await _upsert(scope="global", owner="u1", file_hash="h2")

    assert a.id == b.id
    assert b.file_hash == "h2"
    assert await upload_registry.count_files(scope="global", owner_user_id="u1") == 1


async def test_upsert_same_shared_name_updates_in_place(db_session_scope):
    a = await _upsert(scope="shared", file_hash="h1")
    b = await _upsert(scope="shared", file_hash="h2")

    assert a.id == b.id
    assert await upload_registry.count_files(scope="shared") == 1


# * upsert: distinct rows where the partial-index keys differ


async def test_different_names_are_distinct_rows(db_session_scope):
    # ? Same content, different names -> no cross-name dedup at the registry.
    await _upsert(scope="global", owner="u1", filename="a.js", file_hash="same")
    await _upsert(scope="global", owner="u1", filename="b.js", file_hash="same")

    assert await upload_registry.count_files(scope="global", owner_user_id="u1") == 2


async def test_global_same_filename_different_owners_coexist(db_session_scope):
    await _upsert(scope="global", owner="u1", filename="a.js")
    await _upsert(scope="global", owner="u2", filename="a.js")

    assert await upload_registry.count_files(scope="global", owner_user_id="u1") == 1
    assert await upload_registry.count_files(scope="global", owner_user_id="u2") == 1


async def test_same_filename_across_scopes_coexist(session_id):
    await _upsert(scope="session", session_id=session_id, filename="a.js")
    await _upsert(scope="global", owner="u1", filename="a.js")
    await _upsert(scope="shared", filename="a.js")

    assert await upload_registry.count_files(scope="session", session_id=session_id) == 1
    assert await upload_registry.count_files(scope="global", owner_user_id="u1") == 1
    assert await upload_registry.count_files(scope="shared") == 1


# * check constraint: scope and session_id must agree


async def test_session_scope_requires_session_id(db_session_scope):
    with pytest.raises(IntegrityError):
        await _upsert(scope="session", session_id=None)


async def test_global_scope_rejects_session_id(session_id):
    # ! FK is satisfied (session exists), so the failure is unambiguously the CHECK.
    with pytest.raises(IntegrityError):
        await _upsert(scope="global", owner="u1", session_id=session_id)


# * queries: get / get_by_name / list / count


async def test_get_file_returns_row_or_none(db_session_scope):
    row = await _upsert(scope="shared", filename="a.js")

    fetched = await upload_registry.get_file(row.id)
    assert fetched is not None
    assert fetched.id == row.id
    assert await upload_registry.get_file(uuid4()) is None


async def test_get_by_name_scoped_to_owner(db_session_scope):
    await _upsert(scope="global", owner="u1", filename="a.js")

    assert await upload_registry.get_by_name(scope="global", filename="a.js", owner_user_id="u1") is not None
    assert await upload_registry.get_by_name(scope="global", filename="a.js", owner_user_id="u2") is None


async def test_list_files_scoped_and_ordered(db_session_scope):
    await _upsert(scope="global", owner="u1", filename="b.js")
    await _upsert(scope="global", owner="u1", filename="a.js")
    await _upsert(scope="global", owner="u1", filename="c.js")
    await _upsert(scope="global", owner="u2", filename="z.js")  # different owner, excluded

    rows = await upload_registry.list_files(scope="global", owner_user_id="u1")
    assert [r.filename for r in rows] == ["a.js", "b.js", "c.js"]


async def test_count_files_isolated_per_scope(session_id):
    await _upsert(scope="session", session_id=session_id, filename="a.js")
    await _upsert(scope="session", session_id=session_id, filename="b.js")
    await _upsert(scope="global", owner="u1", filename="a.js")
    await _upsert(scope="shared", filename="a.js")

    assert await upload_registry.count_files(scope="session", session_id=session_id) == 2
    assert await upload_registry.count_files(scope="global", owner_user_id="u1") == 1
    assert await upload_registry.count_files(scope="shared") == 1


# * delete


async def test_delete_file(db_session_scope):
    row = await _upsert(scope="shared", filename="a.js")

    assert await upload_registry.delete_file(row.id) is True
    assert await upload_registry.get_file(row.id) is None
    assert await upload_registry.delete_file(uuid4()) is False


# * mark_missing and the re-upload metadata reset


async def test_mark_missing_sets_flag(db_session_scope):
    row = await _upsert(scope="shared", filename="a.js")

    await upload_registry.mark_missing(row.id)

    refreshed = await upload_registry.get_file(row.id)
    assert refreshed is not None
    assert refreshed.meta_data.get("missing") is True


async def test_reupload_clears_missing_flag(db_session_scope):
    row = await _upsert(scope="shared", filename="a.js", file_hash="h1")
    await upload_registry.mark_missing(row.id)

    # ? Re-upsert of the same name resets meta_data, clearing the stale missing flag.
    await _upsert(scope="shared", filename="a.js", file_hash="h2")

    refreshed = await upload_registry.get_file(row.id)
    assert refreshed is not None
    assert "missing" not in refreshed.meta_data


# * link_message: stamp session files with the message that carried them


async def test_link_message_stamps_session_files(session_id, message_id):
    row = await _upsert(scope="session", session_id=session_id, filename="a.js")

    linked = await upload_registry.link_message(message_id=message_id, file_ids=[row.id], session_id=session_id)
    assert linked == 1

    refreshed = await upload_registry.get_file(row.id)
    assert refreshed is not None
    assert refreshed.message_id == message_id


async def test_link_message_empty_ids_is_noop(session_id, message_id):
    assert await upload_registry.link_message(message_id=message_id, file_ids=[], session_id=session_id) == 0


async def test_link_message_ignores_other_session_files(session_id, message_id):
    row = await _upsert(scope="session", session_id=session_id, filename="a.js")

    # ! A different session's message must not stamp this session's file.
    other = await session_service.create_session(title="other")
    other_message = await session_service.add_message(other.id, "user", {"text": "hi"})

    linked = await upload_registry.link_message(message_id=other_message.id, file_ids=[row.id], session_id=other.id)
    assert linked == 0

    refreshed = await upload_registry.get_file(row.id)
    assert refreshed is not None
    assert refreshed.message_id is None
