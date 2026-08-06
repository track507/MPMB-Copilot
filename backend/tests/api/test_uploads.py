"""
Uploads router - HTTP surface only

UploadService is mocked so these assert the router's own job: multipart parsing, principal threading, the {code, message} error envelope, response shaping, and download headers
No Postgres needed
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.services.uploads.errors import UploadError


def _row(**over):
    """A stand-in File row carrying every field _to_out reads."""
    base = dict(
        id=uuid4(),
        scope="global",
        session_id=None,
        filename="a.js",
        original_filename="a.js",
        file_size=10,
        content_type="text/javascript",
        file_hash="h1",
        uploaded_at=datetime.now(timezone.utc),
        message_id=None,
        meta_data={},
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture
def client(monkeypatch):
    # Endpoints gate on db.is_connected; pretend the DB is up.
    monkeypatch.setattr("app.api.uploads.db", SimpleNamespace(is_connected=True))
    from app.main import app

    return TestClient(app)


@pytest.fixture
def svc(monkeypatch):
    """Mock UploadService + the router's session existence check."""
    store = AsyncMock(return_value=_row())
    list_ = AsyncMock(return_value=[])
    open_ = AsyncMock()
    delete = AsyncMock(return_value=None)
    get_session = AsyncMock(return_value=SimpleNamespace(id=uuid4()))  # default: session exists
    monkeypatch.setattr("app.api.uploads.upload_service.store", store)
    monkeypatch.setattr("app.api.uploads.upload_service.list_with_reconcile", list_)
    monkeypatch.setattr("app.api.uploads.upload_service.open_content", open_)
    monkeypatch.setattr("app.api.uploads.upload_service.delete", delete)
    monkeypatch.setattr("app.api.uploads.session_service.get_session", get_session)
    return SimpleNamespace(store=store, list=list_, open=open_, delete=delete, get_session=get_session)


# * POST /uploads


def test_upload_returns_201_and_threads_principal(client, svc):
    svc.store.return_value = _row(scope="global", filename="a.js")
    resp = client.post(
        "/api/uploads", data={"scope": "global"}, files={"file": ("a.js", b"content", "text/javascript")}
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["filename"] == "a.js"
    assert body["scope"] == "global"
    assert body["missing"] is False

    kw = svc.store.await_args.kwargs
    assert kw["scope"] == "global"
    assert kw["user_id"] == "default"  # from the autouse admin principal
    assert kw["role"] == "admin"
    assert kw["session_id"] is None
    assert kw["upload"].filename == "a.js"


def test_session_upload_proceeds_when_session_exists(client, svc):
    sid = uuid4()
    svc.store.return_value = _row(scope="session", session_id=sid)
    resp = client.post(
        "/api/uploads",
        data={"scope": "session", "session_id": str(sid)},
        files={"file": ("a.js", b"x", "text/javascript")},
    )

    assert resp.status_code == 201
    svc.store.assert_awaited_once()
    assert svc.store.await_args.kwargs["session_id"] == sid


def test_session_upload_unknown_session_is_404(client, svc):
    svc.get_session.return_value = None  # session does not exist
    resp = client.post(
        "/api/uploads",
        data={"scope": "session", "session_id": str(uuid4())},
        files={"file": ("a.js", b"x", "text/javascript")},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"
    svc.store.assert_not_awaited()


def test_unknown_scope_value_is_422(client, svc):
    resp = client.post("/api/uploads", data={"scope": "bogus"}, files={"file": ("a.js", b"x", "text/javascript")})
    assert resp.status_code == 422


@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (400, "invalid_filename"),
        (400, "extension_not_allowed"),
        (400, "empty_file"),
        (400, "invalid_scope"),
        (400, "quota_exceeded"),
        (413, "file_too_large"),
        (403, "forbidden"),
    ],
)
def test_upload_error_surfaces_as_envelope(client, svc, status_code, code):
    svc.store.side_effect = UploadError(status_code, code, "boom")
    resp = client.post("/api/uploads", data={"scope": "global"}, files={"file": ("a.js", b"x", "text/javascript")})

    assert resp.status_code == status_code
    assert resp.json()["detail"] == {"code": code, "message": "boom"}


# * GET /uploads


def test_list_returns_files_with_missing_flag(client, svc):
    svc.list.return_value = [_row(filename="a.js"), _row(filename="b.js", meta_data={"missing": True})]
    resp = client.get("/api/uploads", params={"scope": "global"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert [f["filename"] for f in body["files"]] == ["a.js", "b.js"]
    assert body["files"][0]["missing"] is False
    assert body["files"][1]["missing"] is True


def test_list_error_surfaces_as_envelope(client, svc):
    svc.list.side_effect = UploadError(400, "invalid_scope", "nope")
    resp = client.get("/api/uploads", params={"scope": "global"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_scope"


# * GET /uploads/{id}/content


def test_download_sets_attachment_and_nosniff(client, svc, tmp_path):
    f = tmp_path / "a.js"
    f.write_bytes(b"content")
    svc.open.return_value = (str(f), _row(filename="a.js"))

    resp = client.get(f"/api/uploads/{uuid4()}/content")

    assert resp.status_code == 200
    assert resp.content == b"content"
    assert resp.headers["x-content-type-options"] == "nosniff"
    disposition = resp.headers["content-disposition"]
    assert "attachment" in disposition
    assert "a.js" in disposition


def test_download_missing_surfaces_as_envelope(client, svc):
    svc.open.side_effect = UploadError(404, "file_missing", "gone")
    resp = client.get(f"/api/uploads/{uuid4()}/content")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "file_missing"


# * DELETE /uploads/{id}


def test_delete_returns_204(client, svc):
    fid = uuid4()
    resp = client.delete(f"/api/uploads/{fid}")

    assert resp.status_code == 204
    kw = svc.delete.await_args.kwargs
    assert kw["file_id"] == fid
    assert kw["user_id"] == "default"
    assert kw["role"] == "admin"


def test_delete_not_found_surfaces_as_envelope(client, svc):
    svc.delete.side_effect = UploadError(404, "not_found", "gone")
    resp = client.delete(f"/api/uploads/{uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"


# * DB gate


def test_requires_db_returns_503(client, svc, monkeypatch):
    monkeypatch.setattr("app.api.uploads.db", SimpleNamespace(is_connected=False))
    resp = client.get("/api/uploads", params={"scope": "global"})
    assert resp.status_code == 503
