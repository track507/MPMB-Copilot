"""
Service-key wall abuse cases: the ops wall accepts scoped keys, everything else never does
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def unwalled_client(monkeypatch):
    """main.app WITHOUT the conftest bypass overrides - the real walls."""
    from app.api.deps import current_principal, principal_or_service
    from app.main import app

    app.dependency_overrides.pop(current_principal, None)
    app.dependency_overrides.pop(principal_or_service, None)
    from app.api import deps

    monkeypatch.setattr(deps.config, "auth_disabled", False, raising=False)
    monkeypatch.setattr(deps, "db", SimpleNamespace(is_connected=True))
    yield TestClient(app, raise_server_exceptions=False)


def _mock_key(monkeypatch, scopes):
    from app.api import deps

    key = SimpleNamespace(id=uuid4(), scopes=list(scopes))
    monkeypatch.setattr(deps.api_key_service, "resolve_key", AsyncMock(return_value=key))


BEARER = {"Authorization": "Bearer mpmb_test-token"}


def test_unknown_key_is_401(unwalled_client, monkeypatch):
    from app.api import deps

    monkeypatch.setattr(deps.api_key_service, "resolve_key", AsyncMock(return_value=None))
    assert unwalled_client.post("/api/index", json={}, headers=BEARER).status_code == 401


def test_key_without_scope_is_403_on_index_write(unwalled_client, monkeypatch):
    _mock_key(monkeypatch, scopes=[])
    assert unwalled_client.post("/api/index", json={}, headers=BEARER).status_code == 403


def test_key_with_scope_passes_index_write(unwalled_client, monkeypatch):
    _mock_key(monkeypatch, scopes=["index:write"])
    # ? Store is unreachable in tests; anything but 401/403 proves the wall admitted the key
    assert unwalled_client.post("/api/index", json={}, headers=BEARER).status_code not in (401, 403)


def test_key_reads_index_status(unwalled_client, monkeypatch):
    _mock_key(monkeypatch, scopes=[])
    assert unwalled_client.get("/api/index/status", headers=BEARER).status_code not in (401, 403)


def test_key_never_authenticates_outside_ops_wall(unwalled_client, monkeypatch):
    # ! Ops-only invariant: a leaked ops key cannot read chat history or settings
    _mock_key(monkeypatch, scopes=["index:write"])
    for path in ("/api/sessions", "/api/settings", "/api/capabilities"):
        assert unwalled_client.get(path, headers=BEARER).status_code == 401, path


def test_plain_user_role_cannot_trigger_index(unwalled_client, monkeypatch):
    from app.api import deps

    user = SimpleNamespace(id="u1", role="user", disabled=False)
    monkeypatch.setattr(deps.auth_service, "resolve_session", AsyncMock(return_value=user))
    unwalled_client.cookies.set("mpmb_session", "raw-token")
    assert unwalled_client.post("/api/index", json={}).status_code == 403


def test_key_with_db_down_is_503(unwalled_client, monkeypatch):
    from app.api import deps

    monkeypatch.setattr(deps, "db", SimpleNamespace(is_connected=False))
    assert unwalled_client.post("/api/index", json={}, headers=BEARER).status_code == 503


def test_loopback_bypass_admits_scripts_with_no_key(unwalled_client, monkeypatch):
    # ? AUTH_DISABLED on loopback: ops scripts keep working with no key at all
    from app.api import deps

    monkeypatch.setattr(deps.config, "auth_disabled", True, raising=False)
    monkeypatch.setattr(deps.config, "bind_host", "127.0.0.1", raising=False)
    assert unwalled_client.post("/api/index", json={}).status_code not in (401, 403)
