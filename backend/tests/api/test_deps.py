from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api import deps
from app.api.deps import Principal, current_principal, require_admin


def _request(cookie: str | None = None):
    cookies = {deps.COOKIE_NAME: cookie} if cookie else {}
    return SimpleNamespace(cookies=cookies)


@pytest.fixture(autouse=True)
def _auth_on(monkeypatch):
    # ? Force the real path: bypass off, db connected
    monkeypatch.setattr(deps.config, "auth_disabled", False, raising=False)
    monkeypatch.setattr(deps, "db", SimpleNamespace(is_connected=True))
    yield


@pytest.mark.asyncio
async def test_no_cookie_is_401():
    with pytest.raises(HTTPException) as exc:
        await current_principal(_request())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_db_down_with_cookie_is_503(monkeypatch):
    monkeypatch.setattr(deps, "db", SimpleNamespace(is_connected=False))
    with pytest.raises(HTTPException) as exc:
        await current_principal(_request(cookie="sometoken"))
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_invalid_token_is_401(monkeypatch):
    monkeypatch.setattr(deps.auth_service, "resolve_session", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await current_principal(_request(cookie="forged"))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_yields_principal(monkeypatch):
    user = SimpleNamespace(id="u-1", role="user")
    monkeypatch.setattr(deps.auth_service, "resolve_session", AsyncMock(return_value=user))
    p = await current_principal(_request(cookie="good"))
    assert p == Principal(user_id="u-1", role="user")


@pytest.mark.asyncio
async def test_require_admin_rejects_non_admin():
    with pytest.raises(HTTPException) as exc:
        await require_admin(Principal(user_id="u-1", role="user"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_accepts_admin():
    p = await require_admin(Principal(user_id="u-1", role="admin"))
    assert p.role == "admin"


@pytest.mark.asyncio
async def test_auth_disabled_on_loopback_bypasses(monkeypatch):
    monkeypatch.setattr(deps.config, "auth_disabled", True, raising=False)
    monkeypatch.setattr(deps.config, "bind_host", "127.0.0.1", raising=False)
    p = await current_principal(_request())
    assert p.role == "admin"


@pytest.mark.asyncio
async def test_auth_disabled_ignored_off_loopback(monkeypatch):
    monkeypatch.setattr(deps.config, "auth_disabled", True, raising=False)
    monkeypatch.setattr(deps.config, "bind_host", "0.0.0.0", raising=False)
    with pytest.raises(HTTPException) as exc:
        await current_principal(_request())
    assert exc.value.status_code == 401
