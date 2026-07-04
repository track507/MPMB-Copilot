"""
Auth endpoints: first-run setup, login, logout, state, me

Fail closed (503) when the DB is down
Login errors are uniform and timing-padded; failures feed the Postgres rate limiter
Setup requires the one-time logged token when the server is bound non-loopback
"""

import secrets as _secrets
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.api.deps import COOKIE_NAME, Principal, current_principal, resolve_optional_principal
from app.config import config
from app.core import security
from app.logger import get_logger
from app.services.db import auth_service, db

logger = get_logger(__name__)
router = APIRouter(prefix="/auth")

_UNIFORM_LOGIN_ERROR = "Invalid username or password"


class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=256)
    setup_token: Optional[str] = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def _require_db() -> None:
    if not db.is_connected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication unavailable")


def _cookie_secure(request: Request) -> bool:
    if config.cookie_secure == "always":
        return True
    if config.cookie_secure == "never":
        return False
    # ? auto: trust the effective scheme (uvicorn --proxy-headers makes this correct behind a trusted proxy)
    return request.url.scheme == "https"


def _set_session_cookie(response: Response, request: Request, raw_token: str) -> None:
    from app.settings import settings

    response.set_cookie(
        key=COOKIE_NAME,
        value=raw_token,
        max_age=settings.session_lifetime_days * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(request),
        path="/",
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/state", summary="Auth state for frontend routing")
async def auth_state(request: Request) -> dict[str, Any]:
    from app.api.deps import auth_bypassed

    if auth_bypassed():
        return {"state": "authenticated", "user": {"username": "default", "role": "admin"}}
    _require_db()
    if await auth_service.count_users() == 0:
        return {
            "state": "setup_required",
            "setup_token_required": getattr(request.app.state, "setup_token", None) is not None,
        }
    principal = await resolve_optional_principal(request)
    if principal is not None:
        user = await auth_service.resolve_session(request.cookies.get(COOKIE_NAME, ""))
        return {"state": "authenticated", "user": {"username": user.username, "role": user.role}}
    return {"state": "login_required"}


@router.post("/setup", status_code=status.HTTP_201_CREATED, summary="One-time admin creation")
async def setup(body: SetupRequest, request: Request, response: Response) -> dict[str, Any]:
    _require_db()
    if await auth_service.count_users() > 0:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Setup already completed")
    required = getattr(request.app.state, "setup_token", None)
    if required is not None and not _secrets.compare_digest(body.setup_token or "", required):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A valid setup token is required")
    try:
        user = await auth_service.create_admin(body.username, body.password)
    except IntegrityError:
        # ! Concurrent-setup race: the unique index picked a winner; this request lost
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Setup already completed")
    claimed = await auth_service.claim_orphan_sessions(str(user.id))
    request.app.state.setup_token = None
    raw = await auth_service.create_session(user.id)
    _set_session_cookie(response, request, raw)
    logger.info(f"admin_created username={user.username} claimed_sessions={claimed}")
    return {"username": user.username, "role": user.role}


@router.post("/login", summary="Log in with username and password")
async def login(body: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    _require_db()
    ip = _client_ip(request)
    if await auth_service.too_many_failures(body.username, ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts; try again later",
            headers={"Retry-After": "900"},
        )
    user = await auth_service.get_user_by_username(body.username)
    if user is None:
        security.dummy_verify()  # ? uniform timing for unknown usernames
        await auth_service.record_login_failure(body.username, ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_UNIFORM_LOGIN_ERROR)
    if user.disabled or not user.password_hash or not security.verify_password(user.password_hash, body.password):
        await auth_service.record_login_failure(body.username, ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_UNIFORM_LOGIN_ERROR)
    await auth_service.clear_login_failures(body.username, ip)
    raw = await auth_service.create_session(user.id)
    _set_session_cookie(response, request, raw)
    return {"username": user.username, "role": user.role}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Log out")
async def logout(request: Request, response: Response) -> Response:
    raw = request.cookies.get(COOKIE_NAME)
    if raw and db.is_connected:
        await auth_service.revoke_session(raw)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/me", summary="Current principal")
async def me(principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    return {"user_id": principal.user_id, "role": principal.role}
