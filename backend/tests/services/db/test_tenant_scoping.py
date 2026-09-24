"""
Tenant isolation at the database boundary

These tests are about the negative: what a tenant-filtered query must NOT return
An assertion that the caller sees its own row proves nothing on its own, since an unfiltered query passes it too
"""

from typing import Any, Iterable
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.model.orm import File, Session, Tenant, User
from app.services.db.connection import db


def _ids(rows: Iterable[Any]) -> list[str]:
    """
    Compare identifiers as strings

    asyncpg returns its own pgproto UUID, which does not compare equal to the stdlib UUID the ORM generated
    The two render identically, so a direct comparison fails with a diff that shows no difference
    """
    return [str(row) for row in rows]


async def _seed_two_tenants() -> dict[str, object]:
    """
    Two tenants, one user and one session each, committed

    Returns the ids the assertions need, because the ORM objects expire once their session closes
    """
    async with db.session() as s:
        rows = []
        for slug, name in (("foo", "Foo Corp"), ("bar", "Bar Ltd")):
            tenant = Tenant(slug=slug, name=name)
            s.add(tenant)
            await s.flush()
            rows.append(tenant)
        foo, bar = rows

        users = []
        for username, tenant in (("foo-user", foo), ("bar-user", bar)):
            user = User(username=username, tenant_id=tenant.id)
            s.add(user)
            await s.flush()
            users.append(user)
        foo_user, bar_user = users

        sessions = []
        for title, tenant, owner in (("foo work", foo, foo_user), ("bar work", bar, bar_user)):
            row = Session(title=title, user_id=str(owner.id), tenant_id=tenant.id)
            s.add(row)
            await s.flush()
            sessions.append(row)
        foo_session, bar_session = sessions

        return {
            "foo_tenant": foo.id,
            "bar_tenant": bar.id,
            "foo_user": foo_user.id,
            "bar_user": bar_user.id,
            "foo_session": foo_session.id,
            "bar_session": bar_session.id,
        }


async def test_a_session_query_scoped_to_one_tenant_excludes_another(db_session_scope):
    """
    Two tenants, one session each: a tenant-filtered query returns its own and only its own
    """
    seeded = await _seed_two_tenants()

    async with db.session() as s:
        result = await s.execute(select(Session.id).where(Session.tenant_id == seeded["foo_tenant"]))
        visible = result.scalars().all()

    assert _ids(visible) == _ids([seeded["foo_session"]])
    assert str(seeded["bar_session"]) not in _ids(visible)


async def test_the_same_query_without_a_tenant_filter_sees_both(db_session_scope):
    """
    The control for the test above

    Without this, a query returning one row could mean isolation or could mean only one row existed
    """
    seeded = await _seed_two_tenants()

    async with db.session() as s:
        visible = (await s.execute(select(Session.id))).scalars().all()

    assert set(_ids([seeded["foo_session"], seeded["bar_session"]])) <= set(_ids(visible))


async def test_files_are_scoped_by_tenant_not_only_by_owner(db_session_scope):
    """
    Two users in different tenants: a tenant-filtered file query returns one file

    Owner filtering alone would also pass here, so the query deliberately filters on tenant only
    """
    seeded = await _seed_two_tenants()

    async with db.session() as s:
        for name, owner, tenant, digest in (
            ("foo.js", seeded["foo_user"], seeded["foo_tenant"], "a"),
            ("bar.js", seeded["bar_user"], seeded["bar_tenant"], "b"),
        ):
            s.add(
                File(
                    scope="global",
                    # ? owner_user_id is varchar, so the uuid is stored as its string form
                    owner_user_id=str(owner),
                    tenant_id=tenant,
                    filename=name,
                    original_filename=name,
                    storage_key=f"tenants/{digest}/global/{name}",
                    content_type="text/javascript",
                    file_size=1,
                    file_hash=digest * 64,
                )
            )
            await s.flush()

    async with db.session() as s:
        result = await s.execute(select(File.filename).where(File.tenant_id == seeded["foo_tenant"]))
        visible = result.scalars().all()

    assert visible == ["foo.js"]
    assert "bar.js" not in visible


async def test_a_user_cannot_reference_a_tenant_that_does_not_exist(db_session_scope):
    """
    The foreign key is what makes tenant_id trustworthy downstream

    Without it a typo in a tenant id would read as an empty result rather than as an error
    """
    with pytest.raises(IntegrityError):
        async with db.session() as s:
            s.add(User(username="orphan", tenant_id=uuid4()))
