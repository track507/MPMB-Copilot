"""
The client address behind a trusted reverse proxy

A forwarding header is believed only when the TCP peer is in config.trusted_proxy_cidrs, so a client cannot choose its own address
This middleware is the only layer that reads forwarding headers; every launcher runs uvicorn with --no-proxy-headers
"""

from collections.abc import Sequence
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import config

Network = IPv4Network | IPv6Network


def _address(value: str) -> str | None:
    """The bare IP in a header value or peer, or None when it is not one; tolerates a port, IPv6 brackets and IPv4-mapped IPv6"""
    text = value.strip().strip('"')
    if text.startswith("[") and "]" in text:
        text = text[1 : text.index("]")]
    elif text.count(":") == 1:
        text = text.split(":", 1)[0]
    try:
        address = ip_address(text)
    except ValueError:
        return None
    return str(getattr(address, "ipv4_mapped", None) or address)


def _is_trusted(host: str, networks: Sequence[Network]) -> bool:
    address = _address(host)
    return address is not None and any(ip_address(address) in network for network in networks)


def trusted_networks() -> list[Network]:
    return [ip_network(cidr, strict=False) for cidr in config.trusted_proxy_cidrs]


def resolve_client_ip(peer: str, headers: Headers, *, trusted: Sequence[Network], header: str) -> str:
    """
    The client address for rate limits and audit records

    X-Forwarded-For is read right to left, skipping trusted proxies; the first other hop is the client
    ! Hops left of that one were written by the client and are never believed
    """
    if not _is_trusted(peer, trusted):
        return peer
    if header.lower() == "cf-connecting-ip":
        return _address(headers.get("cf-connecting-ip", "")) or peer
    hops = [hop for value in headers.getlist("x-forwarded-for") for hop in value.split(",") if hop.strip()]
    for hop in reversed(hops):
        address = _address(hop)
        if address is None:
            return peer
        if not _is_trusted(address, trusted):
            return address
    return (_address(hops[0]) or peer) if hops else peer


class TrustedProxyMiddleware:
    """
    Sets the ASGI client to the resolved address and keeps the TCP peer in request.state.socket_peer

    Behind a trusted proxy it also adopts X-Forwarded-Proto, which the Secure cookie decision reads
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            peer = scope["client"][0] if scope.get("client") else ""
            headers = Headers(scope=scope)
            networks = trusted_networks()
            scope.setdefault("state", {})["socket_peer"] = peer
            client = resolve_client_ip(peer, headers, trusted=networks, header=config.client_ip_header)
            if client != peer:
                scope["client"] = (client, 0)
            if _is_trusted(peer, networks):
                proto = headers.get("x-forwarded-proto", "").split(",")[-1].strip().lower()
                if proto in ("http", "https"):
                    scope["scheme"] = proto
        await self.app(scope, receive, send)
