from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api import body_limit
from app.api.body_limit import MULTIPART_OVERHEAD_BYTES, body_limit_for
from app.config import config
from app.settings import settings


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "max_request_body_bytes", 1_000)
    from app.main import app

    return TestClient(app)


def _chunks(total: int, size: int = 256) -> Iterator[bytes]:
    sent = 0
    while sent < total:
        yield b"x" * min(size, total - sent)
        sent += size


def test_the_upload_route_gets_the_file_cap_and_every_other_route_the_json_cap(monkeypatch):
    monkeypatch.setattr(settings, "upload_max_file_bytes", 5_000)
    monkeypatch.setattr(config, "max_request_body_bytes", 100)
    assert body_limit_for("POST", "/api/uploads") == 5_000 + MULTIPART_OVERHEAD_BYTES
    assert body_limit_for("GET", "/api/uploads") == 100
    assert body_limit_for("POST", "/api/chat") == 100


def test_a_declared_oversized_body_is_refused_as_a_problem(client):
    response = client.patch("/api/settings", content=b"x" * 2_000, headers={"content-type": "application/json"})
    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"


def test_a_chunked_body_without_content_length_is_counted_and_refused(client):
    response = client.patch("/api/settings", content=_chunks(2_000), headers={"content-type": "application/json"})
    assert "content-length" not in response.request.headers
    assert response.status_code == 413


def test_a_small_body_reaches_the_route(client):
    assert client.patch("/api/settings", json={}).status_code == 400


def test_an_upload_over_the_file_cap_never_reaches_the_service(client, monkeypatch):
    monkeypatch.setattr(settings, "upload_max_file_bytes", 1_000)
    monkeypatch.setattr(body_limit, "MULTIPART_OVERHEAD_BYTES", 0)
    monkeypatch.setattr("app.api.uploads.db", SimpleNamespace(is_connected=True))
    store = AsyncMock()
    monkeypatch.setattr("app.api.uploads.upload_service.store", store)
    response = client.post("/api/uploads", files={"file": ("a.js", b"x" * 2_000)}, data={"scope": "global"})
    assert response.status_code == 413
    store.assert_not_awaited()


def test_an_upload_exactly_at_the_file_cap_passes_the_body_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "upload_max_file_bytes", 1_000)
    response = client.post("/api/uploads", files={"file": ("a.js", b"x" * 1_000)}, data={"scope": "global"})
    assert response.status_code != 413
