from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError


def _client(monkeypatch, *, users: int = 0, setup_token: str | None = None):
    from app.api import auth as auth_api
    from app.api import deps

    monkeypatch.setattr(deps.config, "auth_disabled", False, raising=False)
    monkeypatch.setattr(auth_api, "db", SimpleNamespace(is_connected=True))
    monkeypatch.setattr(deps, "db", SimpleNamespace(is_connected=True))
    monkeypatch.setattr(auth_api.auth_service, "count_users", AsyncMock(return_value=users))

    app = FastAPI()
    app.state.setup_token = setup_token
    app.include_router(auth_api.router)
    return TestClient(app)


def test_state_setup_required(monkeypatch):
    client = _client(monkeypatch, users=0)
    body = client.get("/auth/state").json()
    assert body["state"] == "setup_required"
    assert body["setup_token_required"] is False


def test_state_setup_token_flagged(monkeypatch):
    client = _client(monkeypatch, users=0, setup_token="tok123")
    body = client.get("/auth/state").json()
    assert body["setup_token_required"] is True


def test_state_login_required(monkeypatch):
    client = _client(monkeypatch, users=1)
    assert client.get("/auth/state").json()["state"] == "login_required"


def test_setup_creates_admin_and_sets_cookie(monkeypatch):
    from app.api import auth as auth_api

    admin = SimpleNamespace(id="admin-id", username="terrence", role="admin")
    monkeypatch.setattr(auth_api.auth_service, "create_admin", AsyncMock(return_value=admin))
    monkeypatch.setattr(auth_api.auth_service, "claim_orphan_sessions", AsyncMock(return_value=3))
    monkeypatch.setattr(auth_api.auth_service, "create_session", AsyncMock(return_value="rawtoken"))

    client = _client(monkeypatch, users=0)
    resp = client.post("/auth/setup", json={"username": "terrence", "password": "a-long-password"})
    assert resp.status_code == 201
    cookie = resp.headers["set-cookie"]
    assert "mpmb_session=rawtoken" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie.lower() or "samesite=lax" in cookie.lower()


def test_setup_403_when_users_exist(monkeypatch):
    client = _client(monkeypatch, users=1)
    resp = client.post("/auth/setup", json={"username": "abc", "password": "a-long-password"})
    assert resp.status_code == 403


def test_setup_requires_token_when_exposed(monkeypatch):
    from app.api import auth as auth_api

    admin = SimpleNamespace(id="admin-id", username="x", role="admin")
    monkeypatch.setattr(auth_api.auth_service, "create_admin", AsyncMock(return_value=admin))
    monkeypatch.setattr(auth_api.auth_service, "claim_orphan_sessions", AsyncMock(return_value=0))
    monkeypatch.setattr(auth_api.auth_service, "create_session", AsyncMock(return_value="rawtoken"))

    client = _client(monkeypatch, users=0, setup_token="tok123")
    # ! Missing and wrong tokens are both rejected; the correct token passes the gate
    assert client.post("/auth/setup", json={"username": "abc", "password": "a-long-password"}).status_code == 403
    assert (
        client.post(
            "/auth/setup", json={"username": "abc", "password": "a-long-password", "setup_token": "nope"}
        ).status_code
        == 403
    )
    ok = client.post("/auth/setup", json={"username": "abc", "password": "a-long-password", "setup_token": "tok123"})
    assert ok.status_code == 201


def test_setup_race_maps_integrity_error_to_403(monkeypatch):
    from app.api import auth as auth_api

    monkeypatch.setattr(
        auth_api.auth_service, "create_admin", AsyncMock(side_effect=IntegrityError("insert", {}, Exception("dup")))
    )
    client = _client(monkeypatch, users=0)
    resp = client.post("/auth/setup", json={"username": "abc", "password": "a-long-password"})
    assert resp.status_code == 403


def test_setup_rejects_short_password(monkeypatch):
    # ? Valid username so the 422 is attributable to the password rule alone
    client = _client(monkeypatch, users=0)
    resp = client.post("/auth/setup", json={"username": "abc", "password": "short"})
    assert resp.status_code == 422


def test_login_success_sets_cookie(monkeypatch):
    from app.api import auth as auth_api
    from app.core import security

    user = SimpleNamespace(id="u1", username="terrence", role="admin", disabled=False, password_hash="$h$")
    monkeypatch.setattr(auth_api.auth_service, "too_many_failures", AsyncMock(return_value=False))
    monkeypatch.setattr(auth_api.auth_service, "get_user_by_username", AsyncMock(return_value=user))
    monkeypatch.setattr(security, "verify_password", lambda h, p: True)
    monkeypatch.setattr(auth_api.auth_service, "clear_login_failures", AsyncMock())
    monkeypatch.setattr(auth_api.auth_service, "create_session", AsyncMock(return_value="rawtoken"))

    client = _client(monkeypatch, users=1)
    resp = client.post("/auth/login", json={"username": "terrence", "password": "whatever-long"})
    assert resp.status_code == 200
    assert resp.json() == {"username": "terrence", "role": "admin"}
    assert "mpmb_session=rawtoken" in resp.headers["set-cookie"]


def test_login_unknown_user_is_uniform_401(monkeypatch):
    from app.api import auth as auth_api

    monkeypatch.setattr(auth_api.auth_service, "too_many_failures", AsyncMock(return_value=False))
    monkeypatch.setattr(auth_api.auth_service, "get_user_by_username", AsyncMock(return_value=None))
    monkeypatch.setattr(auth_api.auth_service, "record_login_failure", AsyncMock())

    client = _client(monkeypatch, users=1)
    resp = client.post("/auth/login", json={"username": "ghost", "password": "whatever-long"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid username or password"


def test_login_disabled_user_is_uniform_401(monkeypatch):
    from app.api import auth as auth_api

    user = SimpleNamespace(id="u1", username="t", role="user", disabled=True, password_hash="$h$")
    monkeypatch.setattr(auth_api.auth_service, "too_many_failures", AsyncMock(return_value=False))
    monkeypatch.setattr(auth_api.auth_service, "get_user_by_username", AsyncMock(return_value=user))
    monkeypatch.setattr(auth_api.auth_service, "record_login_failure", AsyncMock())

    client = _client(monkeypatch, users=1)
    resp = client.post("/auth/login", json={"username": "t", "password": "whatever-long"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid username or password"


def test_login_rate_limited_is_429(monkeypatch):
    from app.api import auth as auth_api

    monkeypatch.setattr(auth_api.auth_service, "too_many_failures", AsyncMock(return_value=True))
    client = _client(monkeypatch, users=1)
    resp = client.post("/auth/login", json={"username": "t", "password": "whatever-long"})
    assert resp.status_code == 429
    assert resp.headers["retry-after"] == "900"


def test_logout_revokes_and_clears(monkeypatch):
    from app.api import auth as auth_api

    revoke = AsyncMock()
    monkeypatch.setattr(auth_api.auth_service, "revoke_session", revoke)
    client = _client(monkeypatch, users=1)
    client.cookies.set("mpmb_session", "rawtoken")
    resp = client.post("/auth/logout")
    assert resp.status_code == 204
    revoke.assert_awaited_once_with("rawtoken")


def test_login_503_when_db_down(monkeypatch):
    from app.api import auth as auth_api

    client = _client(monkeypatch, users=1)
    monkeypatch.setattr(auth_api, "db", SimpleNamespace(is_connected=False))
    resp = client.post("/auth/login", json={"username": "t", "password": "whatever-long"})
    assert resp.status_code == 503
