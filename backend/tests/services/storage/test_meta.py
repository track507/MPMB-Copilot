"""
Breadcrumb writing, reading and the drift walk over the filesystem half

The database half of verify() has its own integration test; everything here runs against a temp storage root
"""

import json
from pathlib import Path

import pytest

from app.config import config
from app.core.storage_keys import DEFAULT_TENANT_ID, library_prefix, tenant_meta_key, tenant_name_index_key
from app.services.storage import meta, verify

TENANT_A = DEFAULT_TENANT_ID
TENANT_B = "019f3400-0000-7000-8000-0000000000bb"


@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    """A temp storage root with the tenants subtree, patched the way the app anchors both"""
    data = tmp_path / "data"
    tenants = data / "tenants"
    tenants.mkdir(parents=True)
    monkeypatch.setattr(config, "data_dir", str(data), raising=False)
    monkeypatch.setattr(config, "tenants_dir", str(tenants), raising=False)
    return data


# * write_meta and read_meta


def test_a_breadcrumb_round_trips(storage_root):
    key = tenant_meta_key(TENANT_A)
    meta.write_meta(key, {"id": TENANT_A, "kind": "tenant"})

    assert meta.read_meta(key) == {"id": TENANT_A, "kind": "tenant"}
    assert (storage_root / key).exists()


def test_writing_creates_the_prefix_it_is_given(storage_root):
    """An object store has no directories, so the writer must not require one to exist first"""
    meta.write_meta("tenants/new-tenant/users/new-user/_meta.json", {"id": "new-user"})

    assert (storage_root / "tenants/new-tenant/users/new-user/_meta.json").exists()


def test_a_failed_meta_write_does_not_raise(storage_root, monkeypatch, caplog):
    """
    ! The row is authoritative, so a breadcrumb failure must never fail the user's upload

    A read-only or full volume is the realistic cause, and the correct response is a log line plus a verify finding
    """

    def _raise(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(meta, "_atomic_write", _raise)
    meta.write_meta(tenant_meta_key(TENANT_A), {"id": TENANT_A})

    assert "could not write breadcrumb" in caplog.text


def test_a_half_written_document_is_never_visible(storage_root, monkeypatch):
    """
    The rename is the commit point

    ? Simulated by failing after the temp file is written but before it is renamed into place
    """
    key = tenant_meta_key(TENANT_A)
    meta.write_meta(key, {"id": TENANT_A, "generation": 1})

    real_replace = meta.os.replace

    def _fail_replace(src, dst):
        raise OSError("interrupted")

    monkeypatch.setattr(meta.os, "replace", _fail_replace)
    meta.write_meta(key, {"id": TENANT_A, "generation": 2})
    monkeypatch.setattr(meta.os, "replace", real_replace)

    assert meta.read_meta(key) == {"id": TENANT_A, "generation": 1}
    assert not list((storage_root / library_prefix(TENANT_A)).parent.glob(".meta-*"))


def test_a_corrupt_breadcrumb_reads_as_absent(storage_root):
    """? It is derived, so the verifier reports it rather than a reader raising on it"""
    key = tenant_meta_key(TENANT_A)
    path = storage_root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    assert meta.read_meta(key) is None


def test_a_missing_breadcrumb_reads_as_absent(storage_root):
    assert meta.read_meta(tenant_meta_key("nobody")) is None


# * the name index


def test_the_name_index_lives_inside_the_tenant(storage_root):
    """
    ! One root-level index would put every tenant's usernames in a single object

    Anyone able to list the bucket could then enumerate other organizations' staff
    """
    meta.write_name_index(TENANT_A, [{"username": "ana", "id": "u1"}])

    written = storage_root / tenant_name_index_key(TENANT_A)
    assert written.exists()
    assert TENANT_A in written.as_posix()
    assert not (storage_root / "by-name.json").exists()


def test_the_name_index_is_ordered_so_it_diffs_cleanly(storage_root):
    meta.write_name_index(TENANT_A, [{"username": "zoe", "id": "u2"}, {"username": "ana", "id": "u1"}])

    names = [entry["username"] for entry in meta.read_meta(tenant_name_index_key(TENANT_A))["users"]]
    assert names == ["ana", "zoe"]


def test_two_tenants_keep_separate_indexes(storage_root):
    meta.write_name_index(TENANT_A, [{"username": "ana", "id": "u1"}])
    meta.write_name_index(TENANT_B, [{"username": "bo", "id": "u2"}])

    a = meta.read_meta(tenant_name_index_key(TENANT_A))
    b = meta.read_meta(tenant_name_index_key(TENANT_B))
    assert [u["username"] for u in a["users"]] == ["ana"]
    assert [u["username"] for u in b["users"]] == ["bo"]


# * keys_on_disk: the filesystem half of the drift walk


def _put(root: Path, key: str, body: bytes = b"x") -> Path:
    path = root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def test_an_object_is_reported_as_its_storage_key(storage_root):
    """The walk must produce exactly what a files row holds, or every object reads as an orphan"""
    key = f"{library_prefix(TENANT_A)}/a.js"
    _put(storage_root, key)

    assert verify.keys_on_disk() == {key}


def test_breadcrumbs_and_the_name_index_are_not_objects(storage_root):
    """? No row ever claims them, so counting them would report orphans that can never be resolved"""
    _put(storage_root, f"{library_prefix(TENANT_A)}/a.js")
    meta.write_meta(tenant_meta_key(TENANT_A), {"id": TENANT_A})
    meta.write_name_index(TENANT_A, [])

    assert verify.keys_on_disk() == {f"{library_prefix(TENANT_A)}/a.js"}


def test_an_in_flight_upload_temp_is_not_an_orphan(storage_root):
    """An upload mid-write has no row yet, and it is swept on its own schedule"""
    _put(storage_root, f"{library_prefix(TENANT_A)}/.upload-abc123")

    assert verify.keys_on_disk() == set()


def test_the_walk_never_leaves_the_tenants_prefix(storage_root):
    """! packs/ and runtime/ hold no tenant objects, and walking them would report the whole corpus as orphaned"""
    _put(storage_root, "packs/mpmb/source_2014/MPMB.js")
    _put(storage_root, "runtime/models/fastembed/model.onnx")
    _put(storage_root, f"{library_prefix(TENANT_A)}/a.js")

    assert verify.keys_on_disk() == {f"{library_prefix(TENANT_A)}/a.js"}


def test_an_absent_tenants_prefix_is_empty_not_an_error(storage_root, monkeypatch):
    """A fresh install has no tenants directory, and prefix existence carries no meaning anyway"""
    monkeypatch.setattr(config, "tenants_dir", str(storage_root / "tenants-that-do-not-exist"), raising=False)

    assert verify.keys_on_disk() == set()


def test_a_tenants_dir_outside_the_storage_root_is_refused(storage_root, tmp_path, monkeypatch):
    """! No key could name such an object, so producing one would silently mislabel every finding"""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "a.js").write_bytes(b"x")
    monkeypatch.setattr(config, "tenants_dir", str(outside), raising=False)

    with pytest.raises(RuntimeError, match="not inside data_dir"):
        verify.keys_on_disk()


# * the report


def test_a_clean_report_says_so_without_listing_anything():
    report = verify.VerifyReport(keys_on_disk=3, rows_in_database=3, breadcrumbs_checked=2)

    rendered = verify.format_report(report)
    assert "No drift found" in rendered
    assert report.ok


def test_every_finding_kind_is_grouped_and_counted():
    report = verify.VerifyReport(
        findings=[
            verify.Finding(verify.ORPHAN_KEY, "tenants/a/library/x.js", "object on disk that no files row claims"),
            verify.Finding(verify.MISSING_KEY, "tenants/a/library/y.js", "files row 1 points at nothing on disk"),
            verify.Finding(verify.STALE_META, "tenants/a/_meta.json", "tenant breadcrumb disagrees on name"),
        ]
    )

    rendered = verify.format_report(report)
    assert "Objects with no row (1)" in rendered
    assert "Rows with no object (1)" in rendered
    assert "Breadcrumbs that disagree with their row (1)" in rendered
    assert "3 finding(s). Nothing was repaired." in rendered
    assert not report.ok


def test_the_report_never_offers_to_repair():
    """! The repair differs per direction, and choosing one silently is how the only copy of an upload is deleted"""
    report = verify.VerifyReport(findings=[verify.Finding(verify.ORPHAN_KEY, "tenants/a/library/x.js", "orphan")])

    rendered = verify.format_report(report).lower()
    assert "nothing was repaired" in rendered
    for word in ("--fix", "--repair", "deleted", "removing"):
        assert word not in rendered


def test_json_on_disk_is_pretty_and_sorted(storage_root):
    """? A breadcrumb is read by humans and diffed by reviewers, so key order must not depend on insertion order"""
    meta.write_meta(tenant_meta_key(TENANT_A), {"kind": "tenant", "id": TENANT_A})

    raw = (storage_root / tenant_meta_key(TENANT_A)).read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert list(json.loads(raw)) == ["id", "kind"]
