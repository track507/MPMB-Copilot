"""
API key service: server-granted service principals for ops scripts

Follows the auth_service idiom (async with db.session()); only token hashes are persisted
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update

from app.core import security
from app.logger import get_logger
from app.model.orm import ApiKey
from app.services.db.connection import db

logger = get_logger(__name__)

# * The enforced scope catalog; grows only when a new operation gets a guard
KNOWN_SCOPES: frozenset[str] = frozenset({"index:write"})

TOKEN_PREFIX = "mpmb_"
# ? Throttle last_used_at writes so a polling script costs at most one UPDATE per minute
LAST_USED_BUMP = timedelta(minutes=1)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_raw_key() -> str:
    return TOKEN_PREFIX + security.generate_token()


def key_state(now: datetime, expires_at: Optional[datetime], revoked_at: Optional[datetime]) -> str:
    """Pure key-liveness rule: revocation wins, then absolute expiry."""
    if revoked_at is not None:
        return "revoked"
    if expires_at is not None and now >= expires_at:
        return "expired"
    return "ok"


class ApiKeyService:
    async def create_key(
        self, name: str, scopes: list[str], created_by: UUID, expires_days: Optional[int]
    ) -> tuple[ApiKey, str]:
        raw = generate_raw_key()
        now = _utcnow()
        row = ApiKey(
            name=name,
            token_hash=security.hash_token(raw),
            token_prefix=raw[:12],
            scopes=scopes,
            created_by=created_by,
            expires_at=now + timedelta(days=expires_days) if expires_days is not None else None,
        )
        async with db.session() as session:
            session.add(row)
        return row, raw

    async def resolve_key(self, raw_token: str) -> Optional[ApiKey]:
        token_hash = security.hash_token(raw_token)
        now = _utcnow()
        async with db.session() as session:
            result = await session.execute(select(ApiKey).where(ApiKey.token_hash == token_hash))
            key = result.scalar_one_or_none()
            if key is None or key_state(now, key.expires_at, key.revoked_at) != "ok":
                return None
            if key.last_used_at is None or now - key.last_used_at > LAST_USED_BUMP:
                await session.execute(update(ApiKey).where(ApiKey.id == key.id).values(last_used_at=now))
            return key

    async def list_keys(self) -> list[ApiKey]:
        async with db.session() as session:
            result = await session.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
            return list(result.scalars().all())

    async def revoke_key(self, key_id: UUID) -> bool:
        async with db.session() as session:
            result = await session.execute(
                update(ApiKey).where(ApiKey.id == key_id, ApiKey.revoked_at.is_(None)).values(revoked_at=_utcnow())
            )
            return bool(result.rowcount or 0)


api_key_service = ApiKeyService()
