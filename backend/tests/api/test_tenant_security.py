from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.deps import Principal, current_principal, is_instance_admin, require_scope
from app.core.storage_keys import DEFAULT_TENANT_ID

OTHER_TENANT = "019f3400-0000-7000-8000-00000000000b"
OPERATOR_ADMIN = Principal(user_id="op", role="admin", tenant_id=DEFAULT_TENANT_ID)
TENANT_ADMIN = Principal(user_id="ta", role="admin", tenant_id=OTHER_TENANT)
MEMBER = Principal(user_id="u1", role="user", tenant_id=DEFAULT_TENANT_ID)


def _client(router, principal: Principal) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[current_principal] = lambda: principal
    app.include_router(router)
    return TestClient(app)


def test_only_the_operator_tenants_admin_is_an_instance_admin():
    assert is_instance_admin(OPERATOR_ADMIN)
    assert not is_instance_admin(TENANT_ADMIN)
    assert not is_instance_admin(MEMBER)


async def test_another_tenants_admin_holds_no_ops_scope():
    check = require_scope("index:write")

    with pytest.raises(HTTPException) as refused:
        await check(TENANT_ADMIN)

    assert refused.value.status_code == 403
    assert await check(OPERATOR_ADMIN) is OPERATOR_ADMIN


@pytest.mark.parametrize("principal", [TENANT_ADMIN, MEMBER])
def test_only_the_instance_admin_changes_instance_settings(principal, monkeypatch):
    from app.api import settings as settings_api
    from app.settings import settings

    updates: list[dict] = []
    monkeypatch.setattr(settings, "update", lambda **kw: updates.append(kw))

    resp = _client(settings_api.router, principal).patch("/settings", json={"temperature": 0.1})

    assert resp.status_code == 403
    assert updates == []


@pytest.mark.parametrize("principal", [TENANT_ADMIN, MEMBER])
def test_only_the_instance_admin_mints_api_keys(principal):
    from app.api import api_keys

    client = _client(api_keys.router, principal)

    assert client.get("/api-keys").status_code == 403
    assert client.post("/api-keys", json={"name": "k", "scopes": ["index:write"]}).status_code == 403


@pytest.fixture
def chat_as(monkeypatch):
    from app.main import app

    def _as(principal: Principal) -> TestClient:
        monkeypatch.setitem(app.dependency_overrides, current_principal, lambda: principal)
        monkeypatch.setattr("app.api.chat.db", SimpleNamespace(is_connected=False))
        return TestClient(app)

    return _as


@pytest.mark.parametrize("override", [{"provider": "openai"}, {"model": "gpt-5"}])
def test_a_member_cannot_choose_the_provider_or_model(chat_as, override):
    resp = chat_as(MEMBER).post("/api/chat", json={"message": "hi", **override})

    assert resp.status_code == 403


def test_the_instance_admin_may_choose_the_provider(chat_as, monkeypatch):
    seen: dict = {}

    async def generate(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            content="ok",
            provider="ollama",
            model="m",
            usage={},
            timing={},
            tools=None,
            retrieval=None,
            stop_reason=None,
        )

    monkeypatch.setattr("app.api.chat.get_rag_engine", lambda: SimpleNamespace(generate=generate))

    resp = chat_as(OPERATOR_ADMIN).post("/api/chat", json={"message": "hi", "provider": "ollama"})

    assert resp.status_code == 200
    assert seen["provider"] == "ollama"


async def test_a_session_title_uses_the_turns_provider(monkeypatch):
    from app.services import title_generator

    captured: dict = {}

    async def fake_generate(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(content="A Title")

    async def no_session(*args, **kwargs):
        return None

    monkeypatch.setattr(title_generator, "agent_generate", fake_generate)
    monkeypatch.setattr(title_generator.session_service, "get_session", no_session)
    monkeypatch.setattr(title_generator.session_service, "update_session", no_session)

    await title_generator.generate_session_title(uuid4(), "hi", "u1", provider="ollama")

    assert captured["provider"] == "ollama"
