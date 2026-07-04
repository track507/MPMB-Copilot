"""
Auth service: users, cookie sessions, and the login rate limiter

Follows the session_service idiom (async with db.session())
Only token hashes are persisted; the raw token exists in the login response cookie and nowhere else
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, func, select, update

from app.core import security
from app.logger import get_logger
from app.model.orm import AuthSession, LoginAttempt, Session, User
from app.services.db.connection import db

logger = get_logger(__name__)

# ? Fixed-window login rate limit
RATE_LIMIT_MAX_FAILURES = 5
RATE_LIMIT_WINDOW = timedelta(minutes=15)
# ? Throttle last_seen_at writes so an active user costs at most one UPDATE per minute
LAST_SEEN_BUMP = timedelta(minutes=1)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def session_state(now: datetime, expires_at: datetime, last_seen_at: datetime, idle_days: int) -> str:
    """Pure session-liveness rule: absolute expiry, then sliding idle window."""
    if now >= expires_at:
        return "expired"
    if now - last_seen_at > timedelta(days=idle_days):
        return "idle"
    return "ok"


class AuthService:
    async def count_users(self) -> int:
        async with db.session() as session:
            result = await session.execute(select(func.count(User.id)))
            return int(result.scalar() or 0)

    async def get_user_by_username(self, username: str) -> Optional[User]:
        async with db.session() as session:
            result = await session.execute(select(User).where(func.lower(User.username) == username.lower()))
            return result.scalar_one_or_none()

    async def create_admin(self, username: str, password: str) -> User:
        # ! IntegrityError from the unique index settles the concurrent-setup race; caller maps it to 403
        user = User(username=username, password_hash=security.hash_password(password), role="admin")
        async with db.session() as session:
            session.add(user)
        return user

    async def claim_orphan_sessions(self, admin_id: str) -> int:
        async with db.session() as session:
            result = await session.execute(update(Session).where(Session.user_id.is_(None)).values(user_id=admin_id))
            return int(result.rowcount or 0)

    async def create_session(self, user_id: UUID) -> str:
        from app.settings import settings

        raw = security.generate_token()
        now = _utcnow()
        row = AuthSession(
            token_hash=security.hash_token(raw),
            user_id=user_id,
            expires_at=now + timedelta(days=settings.session_lifetime_days),
            last_seen_at=now,
        )
        async with db.session() as session:
            session.add(row)
            await session.execute(update(User).where(User.id == user_id).values(last_login=now))
            # ? Opportunistic cleanup: purge expired sessions on every login
            await session.execute(delete(AuthSession).where(AuthSession.expires_at < now))
        return raw

    async def resolve_session(self, raw_token: str) -> Optional[User]:
        from app.settings import settings

        token_hash = security.hash_token(raw_token)
        now = _utcnow()
        async with db.session() as session:
            result = await session.execute(
                select(AuthSession, User)
                .join(User, AuthSession.user_id == User.id)
                .where(AuthSession.token_hash == token_hash)
            )
            row = result.first()
            if row is None:
                return None
            auth_session, user = row
            if user.disabled:
                return None
            if (
                session_state(now, auth_session.expires_at, auth_session.last_seen_at, settings.session_idle_days)
                != "ok"
            ):
                await session.execute(delete(AuthSession).where(AuthSession.id == auth_session.id))
                return None
            if now - auth_session.last_seen_at > LAST_SEEN_BUMP:
                await session.execute(
                    update(AuthSession).where(AuthSession.id == auth_session.id).values(last_seen_at=now)
                )
            return user

    async def revoke_session(self, raw_token: str) -> None:
        async with db.session() as session:
            await session.execute(delete(AuthSession).where(AuthSession.token_hash == security.hash_token(raw_token)))

    async def too_many_failures(self, username: str, client_ip: str) -> bool:
        cutoff = _utcnow() - RATE_LIMIT_WINDOW
        async with db.session() as session:
            result = await session.execute(
                select(func.count(LoginAttempt.id)).where(
                    func.lower(LoginAttempt.username) == username.lower(),
                    LoginAttempt.client_ip == client_ip,
                    LoginAttempt.attempted_at >= cutoff,
                )
            )
            return int(result.scalar() or 0) >= RATE_LIMIT_MAX_FAILURES

    async def record_login_failure(self, username: str, client_ip: str) -> None:
        async with db.session() as session:
            session.add(LoginAttempt(username=username, client_ip=client_ip))

    async def clear_login_failures(self, username: str, client_ip: str) -> None:
        async with db.session() as session:
            await session.execute(
                delete(LoginAttempt).where(
                    func.lower(LoginAttempt.username) == username.lower(), LoginAttempt.client_ip == client_ip
                )
            )


auth_service = AuthService()
