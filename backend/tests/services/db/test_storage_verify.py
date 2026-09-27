"""
The drift report against a real database

The filesystem half has its own unit tests; these prove the two halves are compared on the same keys
A key computed one way here and another way in the service would make every object read as an orphan
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import config
from app.core.storage_keys import library_prefix, session_meta_key, tenant_meta_key, user_meta_key
from app.model.orm import File, Session, Tenant, User
from app.services.db.connection import db
from app.services.storage import meta, verify

pytestmark = pytest.mark.usefixtures("db_session_scope")


@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "tenants").mkdir(parents=True)
    monkeypatch.setattr(config, "data_dir", str(data), raising=False)
    monkeypatch.setattr(config, "tenants_dir", str(data / "tenants"), raising=False)
    return data


async def _seed(tenant_id: str, storage_root: Path) -> dict[str, str]:
    """
    One tenant, one user, one session and one file, with every breadcrumb correctly projected

    Returns the keys the tests then damage, so a defect is introduced rather than assumed
    """
    async with db.session() as s:
        user = User(username="ana", role="user", tenant_id=tenant_id)
        s.add(user)
        await s.flush()
        chat = Session(title="First chat", user_id=str(user.id), tenant_id=tenant_id)
        s.add(chat)
        await s.flush()
        key = f"{library_prefix(tenant_id)}/notes.md"
        s.add(
            File(
                scope="shared",
                owner_user_id=str(user.id),
                filename="notes.md",
                original_filename="notes.md",
                storage_key=key,
                content_type="text/markdown",
                file_size=1,
                file_hash="0" * 64,
                tenant_id=tenant_id,
            )
        )
        user_id, chat_id = str(user.id), str(chat.id)

    async with db.session() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        stored_user = (await s.execute(select(User).where(User.username == "ana"))).scalar_one()
        stored_chat = (await s.execute(select(Session))).scalars().first()
        meta.write_meta(
            tenant_meta_key(tenant_id),
            meta.tenant_meta_payload(
                tenant_id=tenant_id, slug=tenant.slug, name=tenant.name, created_at=tenant.created_at
            ),
        )
        meta.write_meta(
            user_meta_key(tenant_id, user_id),
            meta.user_meta_payload(
                user_id=user_id,
                tenant_id=tenant_id,
                username=stored_user.username,
                role=stored_user.role,
                created_at=stored_user.created_at,
            ),
        )
        meta.write_meta(
            session_meta_key(tenant_id, user_id, chat_id),
            meta.session_meta_payload(
                session_id=chat_id,
                tenant_id=tenant_id,
                user_id=user_id,
                created_at=stored_chat.created_at,
            ),
        )

    path = storage_root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return {"user_id": user_id, "session_id": chat_id, "file_key": key}


async def _report(tenant_id: str, storage_root: Path):
    async with db.session() as s:
        return await verify.verify(s)


async def test_a_consistent_store_reports_nothing(tenant_id, storage_root):
    """
    The control

    Every later test damages this state, so if this one ever fails the others prove nothing
    """
    await _seed(tenant_id, storage_root)

    report = await _report(tenant_id, storage_root)

    assert report.ok, verify.format_report(report)
    assert report.rows_in_database == 1
    assert report.keys_on_disk == 1
    assert report.breadcrumbs_checked == 3


async def test_an_object_with_no_row_is_an_orphan(tenant_id, storage_root):
    """! It may be the only copy of an upload, which is exactly why the tool reports instead of deleting"""
    await _seed(tenant_id, storage_root)
    stray = storage_root / library_prefix(tenant_id) / "nobody-claims-me.js"
    stray.write_bytes(b"x")

    report = await _report(tenant_id, storage_root)

    orphans = report.of_kind(verify.ORPHAN_KEY)
    assert [f.key for f in orphans] == [f"{library_prefix(tenant_id)}/nobody-claims-me.js"]
    assert not report.ok


async def test_a_row_with_no_object_is_a_broken_reference(tenant_id, storage_root):
    seeded = await _seed(tenant_id, storage_root)
    (storage_root / seeded["file_key"]).unlink()

    report = await _report(tenant_id, storage_root)

    missing = report.of_kind(verify.MISSING_KEY)
    assert [f.key for f in missing] == [seeded["file_key"]]


async def test_a_breadcrumb_that_disagrees_with_its_row_is_reported(tenant_id, storage_root):
    """The row is authoritative, so the breadcrumb is what gets called wrong"""
    await _seed(tenant_id, storage_root)
    key = tenant_meta_key(tenant_id)
    stale = meta.read_meta(key)
    stale["name"] = "Renamed Somewhere Else"
    meta.write_meta(key, stale)

    report = await _report(tenant_id, storage_root)

    stale_findings = report.of_kind(verify.STALE_META)
    assert [f.key for f in stale_findings] == [key]
    assert "name" in stale_findings[0].detail


async def test_a_deleted_breadcrumb_is_reported_as_stale(tenant_id, storage_root):
    seeded = await _seed(tenant_id, storage_root)
    key = user_meta_key(tenant_id, seeded["user_id"])
    (storage_root / key).unlink()

    report = await _report(tenant_id, storage_root)

    assert [f.key for f in report.of_kind(verify.STALE_META)] == [key]


async def test_all_three_defects_are_reported_together(tenant_id, storage_root):
    """One pass, three findings, non-zero exit: a run that stopped at the first would hide the other two"""
    seeded = await _seed(tenant_id, storage_root)
    (storage_root / library_prefix(tenant_id) / "orphan.js").write_bytes(b"x")
    (storage_root / seeded["file_key"]).unlink()
    stale = meta.read_meta(tenant_meta_key(tenant_id))
    stale["slug"] = "not-the-slug"
    meta.write_meta(tenant_meta_key(tenant_id), stale)

    report = await _report(tenant_id, storage_root)

    assert len(report.of_kind(verify.ORPHAN_KEY)) == 1
    assert len(report.of_kind(verify.MISSING_KEY)) == 1
    assert len(report.of_kind(verify.STALE_META)) == 1
    assert not report.ok


async def test_a_soft_deleted_session_needs_no_breadcrumb(tenant_id, storage_root):
    """
    A soft-deleted chat is not present, so projecting it would report drift forever

    ? Its files are a separate question: those rows are still rows, and the two directions still have to agree
    """
    seeded = await _seed(tenant_id, storage_root)
    (storage_root / session_meta_key(tenant_id, seeded["user_id"], seeded["session_id"])).unlink()

    async with db.session() as s:
        chat = (await s.execute(select(Session))).scalars().one()
        from datetime import datetime, timezone

        chat.deleted_at = datetime.now(timezone.utc)

    report = await _report(tenant_id, storage_root)

    assert report.breadcrumbs_checked == 2
    assert report.ok, verify.format_report(report)
