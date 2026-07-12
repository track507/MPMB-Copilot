"""
Index status exposes the active task id so any client can attach to a running index
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.services.task_manager import TaskStatus


@pytest.fixture
def client(monkeypatch):
    from app.api import index as index_module
    from app.main import app

    store = SimpleNamespace(
        health_check=AsyncMock(return_value=True),
        collection_info=AsyncMock(return_value={"points_count": 10}),
    )
    monkeypatch.setattr(index_module, "get_vector_store", lambda: store)
    monkeypatch.setattr(index_module.index_status_store, "load", lambda: {"indexed_files": 3})
    return TestClient(app, raise_server_exceptions=False)


def test_task_id_present_while_indexing(client, monkeypatch):
    from app.api import index as index_module

    task = SimpleNamespace(id="t-123", name="index_all_chunks", status=TaskStatus.RUNNING)
    monkeypatch.setattr(index_module.task_manager, "tasks", {"t-123": task})
    body = client.get("/api/index/status").json()
    assert body["status"] == "indexing"
    assert body["task_id"] == "t-123"


def test_task_id_null_when_idle(client, monkeypatch):
    from app.api import index as index_module

    monkeypatch.setattr(index_module.task_manager, "tasks", {})
    body = client.get("/api/index/status").json()
    assert body["status"] == "ready"
    assert body["task_id"] is None
