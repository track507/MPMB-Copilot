from ipaddress import ip_network
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from app.api.client_ip import TrustedProxyMiddleware, resolve_client_ip
from app.config import config

PROXIES = [ip_network("10.0.0.0/8")]
XFF = "X-Forwarded-For"


def test_no_trusted_proxy_ignores_the_header():
    assert resolve_client_ip("10.0.0.9", Headers({XFF: "203.0.113.7"}), trusted=[], header=XFF) == "10.0.0.9"


def test_untrusted_peer_ignores_the_header():
    assert (
        resolve_client_ip("198.51.100.4", Headers({XFF: "203.0.113.7"}), trusted=PROXIES, header=XFF) == "198.51.100.4"
    )


def test_trusted_peer_yields_the_rightmost_untrusted_hop():
    assert resolve_client_ip("10.0.0.9", Headers({XFF: "203.0.113.7"}), trusted=PROXIES, header=XFF) == "203.0.113.7"


def test_spoofed_leftmost_entries_are_ignored():
    headers = Headers({XFF: "6.6.6.6, 1.2.3.4, 203.0.113.7"})
    assert resolve_client_ip("10.0.0.9", headers, trusted=PROXIES, header=XFF) == "203.0.113.7"


def test_a_chain_of_trusted_proxies_is_skipped():
    headers = Headers({XFF: "203.0.113.7, 10.0.0.5"})
    assert resolve_client_ip("10.0.0.9", headers, trusted=PROXIES, header=XFF) == "203.0.113.7"


def test_a_port_suffix_is_tolerated():
    assert (
        resolve_client_ip("10.0.0.9", Headers({XFF: "203.0.113.7:51234"}), trusted=PROXIES, header=XFF) == "203.0.113.7"
    )


def test_cloudflare_header_mode():
    headers = Headers({"CF-Connecting-IP": "2001:db8::7", XFF: "6.6.6.6"})
    assert resolve_client_ip("10.0.0.9", headers, trusted=PROXIES, header="CF-Connecting-IP") == "2001:db8::7"


def test_a_non_ip_peer_is_never_trusted():
    assert resolve_client_ip("testclient", Headers({XFF: "203.0.113.7"}), trusted=PROXIES, header=XFF) == "testclient"


def _probe_app() -> FastAPI:
    app = FastAPI()

    @app.get("/who")
    async def who(request: Request) -> dict[str, str]:
        client = request.client.host if request.client else ""
        return {"client": client, "peer": request.state.socket_peer, "scheme": request.url.scheme}

    app.add_middleware(TrustedProxyMiddleware)
    return app


def test_middleware_rewrites_client_and_scheme_for_a_trusted_peer(monkeypatch):
    monkeypatch.setattr(config, "trusted_proxy_cidrs", ["10.0.0.0/8"], raising=False)
    monkeypatch.setattr(config, "client_ip_header", XFF, raising=False)
    client = TestClient(_probe_app(), client=("10.0.0.9", 40000))
    body = client.get("/who", headers={XFF: "6.6.6.6, 203.0.113.7", "X-Forwarded-Proto": "https"}).json()
    assert body == {"client": "203.0.113.7", "peer": "10.0.0.9", "scheme": "https"}


def test_middleware_leaves_an_untrusted_peer_alone(monkeypatch):
    monkeypatch.setattr(config, "trusted_proxy_cidrs", [], raising=False)
    client = TestClient(_probe_app(), client=("198.51.100.4", 40000))
    body = client.get("/who", headers={XFF: "203.0.113.7", "X-Forwarded-Proto": "https"}).json()
    assert body == {"client": "198.51.100.4", "peer": "198.51.100.4", "scheme": "http"}


def test_login_rate_limit_keys_on_the_resolved_client(monkeypatch):
    from app.api import auth as auth_api

    monkeypatch.setattr(config, "trusted_proxy_cidrs", ["10.0.0.0/8"], raising=False)
    monkeypatch.setattr(config, "client_ip_header", XFF, raising=False)
    monkeypatch.setattr(auth_api, "db", SimpleNamespace(is_connected=True))
    too_many = AsyncMock(return_value=True)
    monkeypatch.setattr(auth_api.auth_service, "too_many_failures", too_many)

    app = FastAPI()
    app.include_router(auth_api.router)
    app.add_middleware(TrustedProxyMiddleware)
    client = TestClient(app, client=("10.0.0.9", 40000))
    response = client.post("/auth/login", json={"username": "abc", "password": "x"}, headers={XFF: "203.0.113.7"})
    assert response.status_code == 429
    too_many.assert_awaited_once_with("abc", "203.0.113.7")
