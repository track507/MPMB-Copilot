"""
API key management endpoints: admin-only, token shown once
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def admin_client():
    """Admin principal with a real UUID (the conftest default 'default' is not a UUID)."""
    from app.api.deps import Principal, current_principal
    from app.main import app

    app.dependency_overrides[current_principal] = lambda: Principal(user_id=str(uuid4()), role="admin")
    yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def user_client():
    from app.api.deps import Principal, current_principal
    from app.main import app

    app.dependency_overrides[current_principal] = lambda: Principal(user_id=str(uuid4()), role="user")
    yield TestClient(app, raise_server_exceptions=False)


def _fake_row(**overrides):
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(
        id=uuid4(),
        name="ops",
        token_prefix="mpmb_abc1234",
        scopes=["index:write"],
        created_at=now,
        expires_at=None,
        last_used_at=None,
        revoked_at=None,
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    return row


def test_mint_returns_token_once(admin_client, monkeypatch):
    from app.api import api_keys as api_keys_module

    row = _fake_row()
    monkeypatch.setattr(api_keys_module.api_key_service, "create_key", AsyncMock(return_value=(row, "mpmb_raw-token")))
    resp = admin_client.post("/api/api-keys", json={"name": "ops"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["token"] == "mpmb_raw-token"
    assert body["scopes"] == ["index:write"]


def test_mint_rejects_unknown_scope(admin_client):
    resp = admin_client.post("/api/api-keys", json={"name": "ops", "scopes": ["settings:write"]})
    assert resp.status_code == 422


def test_mint_requires_real_admin_uuid(monkeypatch):
    # ? Bypass-mode principal has user_id="default": minting must refuse (created_by is a users FK)
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/api-keys", json={"name": "ops"})
    assert resp.status_code == 400


def test_non_admin_cannot_mint(user_client):
    assert user_client.post("/api/api-keys", json={"name": "ops"}).status_code == 403


def test_list_never_contains_tokens(admin_client, monkeypatch):
    from app.api import api_keys as api_keys_module

    monkeypatch.setattr(api_keys_module.api_key_service, "list_keys", AsyncMock(return_value=[_fake_row()]))
    body = admin_client.get("/api/api-keys").json()
    assert body[0]["token_prefix"] == "mpmb_abc1234"
    assert "token" not in body[0]
    assert "token_hash" not in body[0]


def test_revoke_unknown_key_is_404(admin_client, monkeypatch):
    from app.api import api_keys as api_keys_module

    monkeypatch.setattr(api_keys_module.api_key_service, "revoke_key", AsyncMock(return_value=False))
    assert admin_client.delete(f"/api/api-keys/{uuid4()}").status_code == 404
