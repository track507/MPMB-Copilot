"""
Auth dependencies: cookie -> auth session -> Principal

current_principal is the API-wide wall (401 unauthenticated, 503 when the DB is down - fail closed) require_admin layers the role check (403)
auth_disabled is an env-only dev escape honored only on loopback
"""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from app.config import config
from app.services.db import api_key_service, auth_service, db

COOKIE_NAME = "mpmb_session"


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str
    scopes: tuple[str, ...] = ()


_DEFAULT_ADMIN = Principal(user_id="default", role="admin")


def is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def auth_bypassed() -> bool:
    # ! Never allow the escape hatch on an exposed interface
    return config.auth_disabled and is_loopback(config.bind_host)


async def resolve_optional_principal(request: Request) -> Principal | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw or not db.is_connected:
        return None
    user = await auth_service.resolve_session(raw)
    if user is None:
        return None
    return Principal(user_id=str(user.id), role=user.role)


async def current_principal(request: Request) -> Principal:
    if auth_bypassed():
        return _DEFAULT_ADMIN
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if not db.is_connected:
        # ! Fail closed: a cookie we cannot verify is not a login
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication unavailable")
    principal = await resolve_optional_principal(request)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return principal


async def principal_or_service(request: Request) -> Principal:
    """Ops wall: cookie principal OR a server-granted API key (index/tasks routers only)."""
    if auth_bypassed():
        return _DEFAULT_ADMIN
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        if not db.is_connected:
            # ! Fail closed: a key we cannot verify is not a grant
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication unavailable")
        key = await api_key_service.resolve_key(auth_header.removeprefix("Bearer ").strip())
        if key is None:
            # ? Uniform 401: unknown, revoked, and expired are indistinguishable to the caller
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        return Principal(user_id=str(key.id), role="service", scopes=tuple(key.scopes))
    return await current_principal(request)


def require_scope(scope: str):
    """Admins hold all scopes implicitly; service principals need the explicit grant; plain users are refused."""

    async def _check(principal: Principal = Depends(principal_or_service)) -> Principal:
        if principal.role == "admin":
            return principal
        if principal.role == "service" and scope in principal.scopes:
            return principal
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    return _check


async def require_admin(principal: Principal = Depends(current_principal)) -> Principal:
    if principal.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return principal
