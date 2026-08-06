"""
UploadService - disk mechanics, access control, hashing/dedup, reconciliation

The registry seam is mocked (see conftest); these assert the service's own logic against a real temp filesystem
No Postgres required
"""

import hashlib
import os
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.config import config
from app.services.uploads.errors import UploadError
from app.services.uploads.service import upload_service
from app.settings import settings

# * access control (_check_access is pure - no disk, no registry)


def test_check_access_admin_bypasses_all():
    upload_service._check_access(scope="global", row_owner="u2", user_id="u1", role="admin", write=True)
    upload_service._check_access(scope="shared", row_owner="x", user_id="u1", role="admin", write=True)


def test_check_access_global_non_owner_forbidden():
    with pytest.raises(UploadError) as exc:
        upload_service._check_access(scope="global", row_owner="u2", user_id="u1", role="user", write=False)
    assert exc.value.status_code == 403


def test_check_access_global_owner_allowed():
    upload_service._check_access(scope="global", row_owner="u1", user_id="u1", role="user", write=True)


def test_check_access_shared_write_non_admin_forbidden():
    with pytest.raises(UploadError) as exc:
        upload_service._check_access(scope="shared", row_owner="x", user_id="u1", role="user", write=True)
    assert exc.value.status_code == 403


def test_check_access_shared_read_non_admin_allowed():
    upload_service._check_access(scope="shared", row_owner="x", user_id="u1", role="user", write=False)


# * store: scope/session validation (short-circuits before disk or registry)


async def test_store_rejects_unknown_scope(upload_root, registry, make_upload):
    with pytest.raises(UploadError) as exc:
        await upload_service.store(scope="bogus", user_id="u1", role="user", upload=make_upload())
    assert exc.value.code == "invalid_scope"


async def test_store_session_requires_session_id(upload_root, registry, make_upload):
    with pytest.raises(UploadError) as exc:
        await upload_service.store(scope="session", user_id="u1", role="user", upload=make_upload(), session_id=None)
    assert exc.value.code == "invalid_scope"


async def test_store_non_session_rejects_session_id(upload_root, registry, make_upload):
    with pytest.raises(UploadError) as exc:
        await upload_service.store(scope="global", user_id="u1", role="user", upload=make_upload(), session_id=uuid4())
    assert exc.value.code == "invalid_scope"


# * store: the happy path and its failure modes


async def test_store_writes_file_and_registers(upload_root, registry, make_upload):
    data = b"console.log(1)"
    row = await upload_service.store(scope="shared", user_id="u1", role="admin", upload=make_upload(data, "a.js"))

    saved = upload_root / "shared" / "a.js"
    assert saved.read_bytes() == data
    assert not list((upload_root / "shared").glob(".upload-*"))  # temp cleaned

    registry.upsert_file.assert_awaited_once()
    kwargs = registry.upsert_file.call_args.kwargs
    assert kwargs["scope"] == "shared"
    assert kwargs["filename"] == "a.js"
    assert kwargs["original_filename"] == "a.js"
    assert kwargs["file_path"] == "shared/a.js"
    assert kwargs["file_size"] == len(data)
    assert kwargs["file_hash"] == hashlib.sha256(data).hexdigest()
    assert kwargs["content_type"] == "text/javascript"
    assert kwargs["owner_user_id"] == "u1"
    assert row is registry.upsert_file.return_value


async def test_store_quota_exceeded(upload_root, registry, make_upload):
    registry.count_files.return_value = 10_000
    with pytest.raises(UploadError) as exc:
        await upload_service.store(scope="shared", user_id="u1", role="admin", upload=make_upload())
    assert exc.value.code == "quota_exceeded"
    registry.upsert_file.assert_not_awaited()


async def test_store_empty_file_cleans_temp(upload_root, registry, make_upload):
    with pytest.raises(UploadError) as exc:
        await upload_service.store(scope="shared", user_id="u1", role="admin", upload=make_upload(b"", "a.js"))
    assert exc.value.code == "empty_file"
    assert not list((upload_root / "shared").glob(".upload-*"))
    assert not (upload_root / "shared" / "a.js").exists()


async def test_store_too_large_cleans_temp(upload_root, registry, make_upload, monkeypatch):
    monkeypatch.setattr(settings, "upload_max_file_bytes", 4)
    with pytest.raises(UploadError) as exc:
        await upload_service.store(scope="shared", user_id="u1", role="admin", upload=make_upload(b"toolong", "a.js"))
    assert exc.value.code == "file_too_large"
    assert exc.value.status_code == 413
    assert not list((upload_root / "shared").glob(".upload-*"))


async def test_store_dedup_skips_disk_rewrite(upload_root, registry, make_upload):
    data = b"same-content"
    shared = upload_root / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    target = shared / "a.js"
    target.write_bytes(data)
    original_mtime = target.stat().st_mtime_ns
    registry.get_by_name.return_value = SimpleNamespace(id=uuid4(), file_hash=hashlib.sha256(data).hexdigest())

    await upload_service.store(scope="shared", user_id="u1", role="admin", upload=make_upload(data, "a.js"))

    assert target.read_bytes() == data
    assert target.stat().st_mtime_ns == original_mtime  # no os.replace: disk untouched
    registry.upsert_file.assert_awaited_once()  # row still refreshed
    assert not list(shared.glob(".upload-*"))  # temp cleaned


async def test_store_orphan_cleanup_on_registry_failure(upload_root, registry, make_upload):
    registry.upsert_file.side_effect = RuntimeError("db down")
    with pytest.raises(RuntimeError):
        await upload_service.store(scope="shared", user_id="u1", role="admin", upload=make_upload(b"data", "a.js"))
    assert not (upload_root / "shared" / "a.js").exists()  # renamed file removed
    assert not list((upload_root / "shared").glob(".upload-*"))


# * list_with_reconcile: flag rows whose bytes vanished


async def test_list_rejects_unknown_scope(upload_root, registry):
    with pytest.raises(UploadError) as exc:
        await upload_service.list_with_reconcile(scope="nope", user_id="u1", role="user")
    assert exc.value.code == "invalid_scope"


async def test_list_reconcile_flags_missing(upload_root, registry):
    shared = upload_root / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "present.js").write_bytes(b"x")
    present = SimpleNamespace(id=uuid4(), file_path="shared/present.js", meta_data={})
    missing = SimpleNamespace(id=uuid4(), file_path="shared/missing.js", meta_data={})
    already = SimpleNamespace(id=uuid4(), file_path="shared/gone.js", meta_data={"missing": True})
    registry.list_files.return_value = [present, missing, already]

    rows = await upload_service.list_with_reconcile(scope="shared", user_id="u1", role="user")

    assert rows == [present, missing, already]
    registry.mark_missing.assert_awaited_once_with(missing.id)  # only the newly-missing row
    assert missing.meta_data.get("missing") is True
    assert present.meta_data == {}


# * open_content: authz + on-disk containment and existence


async def test_open_content_not_found(upload_root, registry):
    registry.get_file.return_value = None
    with pytest.raises(UploadError) as exc:
        await upload_service.open_content(file_id=uuid4(), user_id="u1", role="user")
    assert exc.value.status_code == 404
    assert exc.value.code == "not_found"


async def test_open_content_forbidden_for_other_owner(upload_root, registry):
    registry.get_file.return_value = SimpleNamespace(
        id=uuid4(), scope="global", owner_user_id="u2", file_path="global/u2/a.js"
    )
    with pytest.raises(UploadError) as exc:
        await upload_service.open_content(file_id=uuid4(), user_id="u1", role="user")
    assert exc.value.status_code == 403


async def test_open_content_rejects_path_traversal(upload_root, registry):
    registry.get_file.return_value = SimpleNamespace(
        id=uuid4(), scope="shared", owner_user_id="u1", file_path="../escape.js"
    )
    with pytest.raises(UploadError) as exc:
        await upload_service.open_content(file_id=uuid4(), user_id="u1", role="user")
    assert exc.value.code == "not_found"


async def test_open_content_missing_on_disk_marks_missing(upload_root, registry):
    row = SimpleNamespace(id=uuid4(), scope="shared", owner_user_id="u1", file_path="shared/gone.js")
    registry.get_file.return_value = row
    with pytest.raises(UploadError) as exc:
        await upload_service.open_content(file_id=row.id, user_id="u1", role="user")
    assert exc.value.code == "file_missing"
    registry.mark_missing.assert_awaited_once_with(row.id)


async def test_open_content_returns_path_and_row(upload_root, registry):
    shared = upload_root / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "a.js").write_bytes(b"x")
    row = SimpleNamespace(id=uuid4(), scope="shared", owner_user_id="u1", file_path="shared/a.js")
    registry.get_file.return_value = row

    resolved, returned = await upload_service.open_content(file_id=row.id, user_id="u1", role="user")

    assert returned is row
    assert resolved == (shared / "a.js").resolve()


# * delete: authz + disk and row removal


async def test_delete_not_found(upload_root, registry):
    registry.get_file.return_value = None
    with pytest.raises(UploadError) as exc:
        await upload_service.delete(file_id=uuid4(), user_id="u1", role="user")
    assert exc.value.status_code == 404


async def test_delete_shared_non_admin_forbidden(upload_root, registry):
    registry.get_file.return_value = SimpleNamespace(
        id=uuid4(), scope="shared", owner_user_id="u1", file_path="shared/a.js"
    )
    with pytest.raises(UploadError) as exc:
        await upload_service.delete(file_id=uuid4(), user_id="u1", role="user")
    assert exc.value.status_code == 403


async def test_delete_removes_disk_and_row(upload_root, registry):
    g = upload_root / "global" / "u1"
    g.mkdir(parents=True, exist_ok=True)
    (g / "a.js").write_bytes(b"x")
    row = SimpleNamespace(id=uuid4(), scope="global", owner_user_id="u1", file_path="global/u1/a.js")
    registry.get_file.return_value = row

    await upload_service.delete(file_id=row.id, user_id="u1", role="user")

    assert not (g / "a.js").exists()
    registry.delete_file.assert_awaited_once_with(row.id)


# * sweep_stale_temps: startup cleanup of abandoned .upload-* temps


def test_sweep_removes_old_temps_keeps_recent(upload_root):
    old = upload_root / ".upload-old"
    recent = upload_root / ".upload-recent"
    normal = upload_root / "keep.js"
    for p in (old, recent, normal):
        p.write_bytes(b"x")
    past = time.time() - (25 * 3600)
    os.utime(old, (past, past))

    removed = upload_service.sweep_stale_temps()

    assert removed == 1
    assert not old.exists()
    assert recent.exists()
    assert normal.exists()


def test_sweep_missing_dir_returns_zero(upload_root, monkeypatch):
    monkeypatch.setattr(config, "upload_dir", str(upload_root / "does-not-exist"))
    assert upload_service.sweep_stale_temps() == 0
