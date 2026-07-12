"""
API key management: mint/list/revoke service keys (admin-only)

The raw token appears exactly once, in the mint response; only its hash is stored
"""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import Principal, require_admin
from app.logger import get_logger
from app.services.db import api_key_service
from app.services.db.api_key_service import KNOWN_SCOPES

logger = get_logger(__name__)
router = APIRouter(prefix="/api-keys")


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    scopes: list[str] = Field(default_factory=lambda: ["index:write"], min_length=1)
    expires_days: Optional[int] = Field(None, ge=1, le=3650)


def _serialize(key: Any) -> dict[str, Any]:
    return {
        "id": str(key.id),
        "name": key.name,
        "token_prefix": key.token_prefix,
        "scopes": list(key.scopes),
        "created_at": key.created_at,
        "expires_at": key.expires_at,
        "last_used_at": key.last_used_at,
        "revoked_at": key.revoked_at,
    }


@router.post("", status_code=status.HTTP_201_CREATED, summary="Mint a service API key")
async def create_api_key(body: ApiKeyCreate, admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    unknown = set(body.scopes) - KNOWN_SCOPES
    if unknown:
        # HTTP_422_UNPROCESSABLE_ENTITY is deprecated, use HTTP_422_UNPROCESSABLE_CONTENT
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Unknown scopes: {sorted(unknown)}"
        )
    try:
        created_by = UUID(admin.user_id)
    except ValueError:
        # ! Bypass-mode principal is not a persisted user; a key row needs a real creator
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Minting requires a real admin login (auth bypass is active)",
        )
    key, raw = await api_key_service.create_key(body.name, body.scopes, created_by, body.expires_days)
    logger.info(f"api_key_created name={body.name} prefix={key.token_prefix} scopes={body.scopes}")
    return {**_serialize(key), "token": raw}


@router.get("", summary="List API keys (prefixes only)")
async def list_api_keys(_: Principal = Depends(require_admin)) -> list[dict[str, Any]]:
    return [_serialize(k) for k in await api_key_service.list_keys()]


@router.delete("/{key_id}", summary="Revoke an API key")
async def revoke_api_key(key_id: UUID, _: Principal = Depends(require_admin)) -> dict[str, str]:
    revoked = await api_key_service.revoke_key(key_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found or already revoked")
    logger.info(f"api_key_revoked id={key_id}")
    return {"status": "revoked"}
