import os

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.model.orm import Base
from app.services.db.connection import db

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
_TABLES = "files, messages, sessions"  # child-first isn't required with CASCADE


@pytest_asyncio.fixture
async def db_session_scope():
    """
    Connect to a throwaway Postgres, ensure schema, hand each test a clean slate

    Function-scoped on purpose: pytest-asyncio's default event loop is per-test, so the connection pool must be created and disposed inside the same test's loop
    The database persists between tests, so create_all(checkfirst) is a no-op after the first run and TRUNCATE does the isolating
    """
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set - this integration test needs a throwaway Postgres")

    await db.connect(TEST_DATABASE_URL, pool_size=1, max_overflow=0)
    try:
        async with db._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)  # cheap no-op once tables exist
            await conn.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
        yield
    finally:
        await db.disconnect()


@pytest_asyncio.fixture
async def session_id(db_session_scope):
    """
    A committed parent session; session-scope files FK to it. Global/shared tests skip this
    """
    from app.model.orm import Session

    async with db.session() as s:
        row = Session(title="test")
        s.add(row)
        await s.flush()  # assigns row.id (uuid7 default) before commit
        return row.id


@pytest_asyncio.fixture
async def message_id(session_id):
    """
    A committed message inside `session_id`; link_message stamps rows with it
    """
    from app.services.db import session_service

    message = await session_service.add_message(session_id, "user", {"text": "hi"})
    return message.id
