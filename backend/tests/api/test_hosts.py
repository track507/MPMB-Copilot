import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.hosts import HostAllowlistMiddleware, host_allowed
from app.config import config

LOOPBACK = ["localhost", "127.0.0.1", "::1"]


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("127.0.0.1:8000", True),
        ("localhost", True),
        ("LOCALHOST:5173", True),
        ("[::1]:8000", True),
        ("rebind.attacker.example:8000", False),
        ("192.168.1.20:8000", False),
        ("", False),
    ],
)
def test_loopback_allowlist(header, expected):
    assert host_allowed(header, LOOPBACK) is expected


def test_wildcard_matches_subdomains_only():
    assert host_allowed("acme.nabe.example", ["*.nabe.example"])
    assert not host_allowed("nabe.example.evil.test", ["*.nabe.example"])


def test_star_allows_any_host():
    assert host_allowed("anything.test", ["*"])


def _client(base_url: str) -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(HostAllowlistMiddleware)
    return TestClient(app, base_url=base_url)


def test_middleware_serves_an_allowed_host(monkeypatch):
    monkeypatch.setattr(config, "allowed_hosts", LOOPBACK, raising=False)
    assert _client("http://127.0.0.1:8000").get("/ping").status_code == 200


def test_middleware_refuses_a_rebound_host(monkeypatch):
    monkeypatch.setattr(config, "allowed_hosts", LOOPBACK, raising=False)
    response = _client("http://rebind.attacker.example:8000").get("/ping")
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
