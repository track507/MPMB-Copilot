"""
Host header allowlist, the defense against DNS rebinding

A page rebound to 127.0.0.1 is same-origin with itself, so CORS and SameSite do not apply, but its requests still carry the attacker's hostname
"""

from collections.abc import Sequence

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.problem import problem_response, type_for
from app.config import config


def host_allowed(host_header: str, allowed: Sequence[str]) -> bool:
    """
    Whether a Host header names a host this server answers for

    Accepts host, host:port, [ipv6] and [ipv6]:port; a pattern "*.example.com" matches subdomains only
    """
    host = host_header.strip().lower()
    if host.startswith("["):
        host = host[1 : host.find("]")] if "]" in host else ""
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    for pattern in (p.strip().lower() for p in allowed):
        if pattern == "*":
            return True
        if host and (host == pattern or (pattern.startswith("*.") and host.endswith(pattern[1:]))):
            return True
    return False


class HostAllowlistMiddleware:
    """
    Answers 400 to any HTTP request whose Host is not in config.allowed_hosts

    ! Reads the allowlist per request, so a changed config takes effect without a restart
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not host_allowed(Headers(scope=scope).get("host", ""), config.allowed_hosts):
            response = problem_response(
                status=400,
                title="Invalid host",
                detail="This server does not answer for the requested host",
                type=type_for("invalid_host"),
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
