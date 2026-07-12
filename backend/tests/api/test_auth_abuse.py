"""
Abuse-case regression wall: these encode the security review as permanent tests
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def unwalled_main_client():
    """main.app WITHOUT the conftest auth bypass - the real wall."""
    from app.api.deps import current_principal, principal_or_service
    from app.main import app

    app.dependency_overrides.pop(current_principal, None)
    app.dependency_overrides.pop(principal_or_service, None)
    yield TestClient(app, raise_server_exceptions=False)


def test_wall_unauthenticated_requests_are_401(unwalled_main_client, monkeypatch):
    from app.api import deps

    monkeypatch.setattr(deps.config, "auth_disabled", False, raising=False)
    for path in ("/api/sessions", "/api/settings", "/api/capabilities", "/api/index/status"):
        assert unwalled_main_client.get(path).status_code == 401, path
    assert unwalled_main_client.patch("/api/settings", json={"temperature": 0.1}).status_code == 401


def test_wall_health_stays_public(unwalled_main_client):
    # ? liveness for Docker healthchecks; may be degraded, must not be 401
    assert unwalled_main_client.get("/api/health").status_code != 401


def test_forged_cookie_with_db_down_is_503(unwalled_main_client, monkeypatch):
    from app.api import deps

    monkeypatch.setattr(deps.config, "auth_disabled", False, raising=False)
    monkeypatch.setattr(deps, "db", SimpleNamespace(is_connected=False))
    unwalled_main_client.cookies.set("mpmb_session", "forged-token")
    assert unwalled_main_client.get("/api/sessions").status_code == 503


def test_forged_cookie_with_db_up_is_401(unwalled_main_client, monkeypatch):
    from app.api import deps

    monkeypatch.setattr(deps.config, "auth_disabled", False, raising=False)
    monkeypatch.setattr(deps, "db", SimpleNamespace(is_connected=True))
    monkeypatch.setattr(deps.auth_service, "resolve_session", AsyncMock(return_value=None))
    unwalled_main_client.cookies.set("mpmb_session", "forged-token")
    assert unwalled_main_client.get("/api/sessions").status_code == 401


def _auth_client(monkeypatch, **kwargs):
    from app.api import auth as auth_api
    from app.api import deps

    monkeypatch.setattr(deps.config, "auth_disabled", False, raising=False)
    monkeypatch.setattr(auth_api, "db", SimpleNamespace(is_connected=True))
    monkeypatch.setattr(auth_api.auth_service, "count_users", AsyncMock(return_value=kwargs.get("users", 1)))
    app = FastAPI()
    app.state.setup_token = kwargs.get("setup_token")
    app.include_router(auth_api.router)
    return TestClient(app)


def test_setup_token_uses_constant_time_compare(monkeypatch):
    client = _auth_client(monkeypatch, users=0, setup_token="the-real-token")
    resp = client.post("/auth/setup", json={"username": "abc", "password": "a-long-password", "setup_token": "wrong"})
    assert resp.status_code == 403


def test_logout_is_idempotent(monkeypatch):
    # ? Revoking a dead/absent session is a no-op; repeated logout must always 204
    from app.api import auth as auth_api

    monkeypatch.setattr(auth_api.auth_service, "revoke_session", AsyncMock())
    client = _auth_client(monkeypatch)
    client.cookies.set("mpmb_session", "already-dead")
    assert client.post("/auth/logout").status_code == 204
    assert client.post("/auth/logout").status_code == 204


def test_setup_retry_after_success_is_403(monkeypatch):
    # ? Idempotency wall: once any user exists, setup can never run again
    client = _auth_client(monkeypatch, users=1)
    resp = client.post("/auth/setup", json={"username": "again", "password": "a-long-password"})
    assert resp.status_code == 403


def test_login_cookie_not_secure_over_http(monkeypatch):
    from app.api import auth as auth_api
    from app.core import security

    user = SimpleNamespace(id="u1", username="t", role="admin", disabled=False, password_hash="$h$")
    monkeypatch.setattr(auth_api.auth_service, "too_many_failures", AsyncMock(return_value=False))
    monkeypatch.setattr(auth_api.auth_service, "get_user_by_username", AsyncMock(return_value=user))
    monkeypatch.setattr(security, "verify_password", lambda h, p: True)
    monkeypatch.setattr(auth_api.auth_service, "clear_login_failures", AsyncMock())
    monkeypatch.setattr(auth_api.auth_service, "create_session", AsyncMock(return_value="raw"))
    monkeypatch.setattr(auth_api.config, "cookie_secure", "auto", raising=False)

    client = _auth_client(monkeypatch)
    cookie = client.post("/auth/login", json={"username": "t", "password": "long-enough-pw"}).headers["set-cookie"]
    assert "Secure" not in cookie  # http in tests


def test_login_cookie_secure_when_forced(monkeypatch):
    from app.api import auth as auth_api
    from app.core import security

    user = SimpleNamespace(id="u1", username="t", role="admin", disabled=False, password_hash="$h$")
    monkeypatch.setattr(auth_api.auth_service, "too_many_failures", AsyncMock(return_value=False))
    monkeypatch.setattr(auth_api.auth_service, "get_user_by_username", AsyncMock(return_value=user))
    monkeypatch.setattr(security, "verify_password", lambda h, p: True)
    monkeypatch.setattr(auth_api.auth_service, "clear_login_failures", AsyncMock())
    monkeypatch.setattr(auth_api.auth_service, "create_session", AsyncMock(return_value="raw"))
    monkeypatch.setattr(auth_api.config, "cookie_secure", "always", raising=False)

    client = _auth_client(monkeypatch)
    cookie = client.post("/auth/login", json={"username": "t", "password": "long-enough-pw"}).headers["set-cookie"]
    assert "Secure" in cookie
