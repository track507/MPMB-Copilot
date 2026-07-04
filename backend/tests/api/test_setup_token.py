from unittest.mock import AsyncMock

import pytest

from app.main import _init_setup_token


@pytest.mark.asyncio
async def test_exposed_bind_with_no_users_generates_token(monkeypatch):
    from app import main as main_mod

    monkeypatch.setattr(main_mod.config, "bind_host", "0.0.0.0", raising=False)
    monkeypatch.setattr(main_mod.auth_service, "count_users", AsyncMock(return_value=0))
    token = await _init_setup_token()
    assert token is not None and len(token) >= 16


@pytest.mark.asyncio
async def test_loopback_bind_needs_no_token(monkeypatch):
    from app import main as main_mod

    monkeypatch.setattr(main_mod.config, "bind_host", "127.0.0.1", raising=False)
    monkeypatch.setattr(main_mod.auth_service, "count_users", AsyncMock(return_value=0))
    assert await _init_setup_token() is None


@pytest.mark.asyncio
async def test_existing_admin_needs_no_token(monkeypatch):
    from app import main as main_mod

    monkeypatch.setattr(main_mod.config, "bind_host", "0.0.0.0", raising=False)
    monkeypatch.setattr(main_mod.auth_service, "count_users", AsyncMock(return_value=1))
    assert await _init_setup_token() is None
