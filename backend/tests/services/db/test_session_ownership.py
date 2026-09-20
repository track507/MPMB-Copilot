"""
Owner filtering on session queries - the tenant isolation wall

No database: db.session() is replaced with a recorder, so these assert the SQL the service actually builds
That catches the regression that matters - someone drops the predicate - in about a second, and it runs in CI, unlike TEST_DATABASE_URL tests
"""

import sys
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.services.db import session_service
from app.services.db.connection import db

ALICE = "11111111-1111-1111-1111-111111111111"


class _Result:
    """
    Enough of a SQLAlchemy Result for these code paths
    """

    def scalar_one_or_none(self):
        return None

    def scalar_one(self):
        return 0

    def scalars(self):
        return self

    def all(self):
        return []

    @property
    def rowcount(self):
        return 0


class _CapturingSession:
    def __init__(self, statements, added):
        self.statements = statements
        self.added = added

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        return _Result()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, obj):
        return None


@pytest.fixture
def sql(monkeypatch):
    """
    Record every statement the service executes, plus anything it adds

    Patches the attribute on the shared db object rather than rebinding a module name, so every module holding a reference sees the recorder
    """
    statements: list = []
    added: list = []

    @asynccontextmanager
    async def fake_session():
        yield _CapturingSession(statements, added)

    monkeypatch.setattr(db, "session", fake_session)
    return type("Recorder", (), {"statements": statements, "added": added})()


def _compiled(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _owner_filter_in(statement) -> bool:
    return f"sessions.user_id = '{ALICE}'" in _compiled(statement)


async def test_create_stamps_the_owner(sql):
    await session_service.create_session(title="Alice chat", user_id=ALICE)
    assert [row.user_id for row in sql.added] == [ALICE]


async def test_get_session_filters_by_owner(sql):
    await session_service.get_session(uuid4(), user_id=ALICE)
    assert _owner_filter_in(sql.statements[0])


async def test_get_session_with_messages_filters_by_owner(sql):
    await session_service.get_session_with_messages(uuid4(), user_id=ALICE)
    assert _owner_filter_in(sql.statements[0])


async def test_list_sessions_filters_by_owner(sql):
    await session_service.list_sessions(user_id=ALICE)
    assert _owner_filter_in(sql.statements[0])


async def test_session_count_filters_by_owner(sql):
    await session_service.get_session_count(user_id=ALICE)
    assert _owner_filter_in(sql.statements[0])


async def test_update_filters_on_both_statements(sql):
    await session_service.update_session(uuid4(), user_id=ALICE, title="renamed")
    # ! Both: the UPDATE and the re-select, or a non-owner reads the row back unchanged
    assert len(sql.statements) == 2
    assert all(_owner_filter_in(s) for s in sql.statements)


async def test_delete_filters_by_owner(sql):
    await session_service.delete_session(uuid4(), user_id=ALICE)
    assert _owner_filter_in(sql.statements[0])


async def test_get_messages_gates_before_reading(sql):
    result = await session_service.get_messages(uuid4(), user_id=ALICE)
    # ? The gate short-circuits: the ownership SELECT runs, the message SELECT never does
    assert result == []
    assert len(sql.statements) == 1
    assert _owner_filter_in(sql.statements[0])


async def test_conversation_history_gates_before_reading(sql):
    result = await session_service.get_conversation_history(uuid4(), user_id=ALICE)
    assert result == []
    assert len(sql.statements) == 1
    assert _owner_filter_in(sql.statements[0])


async def test_the_assertions_have_teeth(sql, monkeypatch):
    """
    Mutation check: neutering _owned() must make the assertions above fail

    Without this, a typo in the expected substring would make every test above pass against code with no filter at all
    """
    module = sys.modules[type(session_service).__module__]
    monkeypatch.setattr(module, "_owned", lambda user_id: [])

    await session_service.get_session(uuid4(), user_id=ALICE)
    assert not _owner_filter_in(sql.statements[0])


async def test_every_session_method_requires_an_owner(sql):
    """
    A caller cannot forget the owner: omitting it is a TypeError, not an unscoped query

    This is the control that an optional user_id parameter silently loses
    """
    sid = uuid4()
    calls = [
        lambda: session_service.create_session(title="x"),
        lambda: session_service.get_session(sid),
        lambda: session_service.get_session_with_messages(sid),
        lambda: session_service.list_sessions(),
        lambda: session_service.get_session_count(),
        lambda: session_service.update_session(sid, title="x"),
        lambda: session_service.delete_session(sid),
        lambda: session_service.get_messages(sid),
        lambda: session_service.get_conversation_history(sid),
    ]
    for call in calls:
        with pytest.raises(TypeError):
            await call()
