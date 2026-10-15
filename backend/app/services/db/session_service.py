"""Session persistence service.

Handles CRUD for sessions and messages, plus retrieval tracking.
All operations use the async database pool from `database.py`.

Usage:
    from app.services.db import session_service

    session = await session_service.create_session(title="My Chat", user_id=user_id, tenant_id=tenant_id)
    msg = await session_service.add_message(session.id, "user", {"text": "Hello"}, user_id=user_id)
    history = await session_service.get_messages(session.id, user_id=user_id)
"""

from datetime import datetime, timezone
from typing import Any, Optional, cast
from uuid import UUID

from sqlalchemy import ColumnElement, CursorResult, func, select, update
from sqlalchemy.orm import selectinload

from app.core.storage_keys import session_meta_key
from app.logger import get_logger
from app.model.orm import Message, Session
from app.services.db.connection import db
from app.services.storage import meta
from app.settings import settings

logger = get_logger(__name__)


def _owned(user_id: str) -> list[ColumnElement[bool]]:
    """
    Owner predicate for every session-scoped query

    Admins deliberately do not bypass this: chat history is personal data
    That differs from uploads, where role == "admin" bypasses (services/uploads/service.py:46)
    """
    return [Session.user_id == user_id]


def _history_window(newest_first: list[Message], *, max_chars: int) -> list[dict[str, Any]]:
    """
    The newest turns that fit max_chars, oldest first, formatted for the model

    The newest turn is admitted even when it alone exceeds the budget
    """
    window: list[dict[str, Any]] = []
    used = 0
    for msg in newest_first:
        text = msg.content.get("text", "") if isinstance(msg.content, dict) else str(msg.content)
        if not text or msg.role not in ("user", "assistant"):
            continue
        used += len(text)
        if window and used > max_chars:
            break
        window.append({"role": msg.role, "content": text})
    window.reverse()
    # ! A leading assistant turn has lost the question it answers
    while window and window[0]["role"] != "user":
        window.pop(0)
    return window


class SessionService:
    """Session and message persistence."""

    # * Sessions
    async def create_session(
        self,
        title: str = "New Conversation",
        edition: Optional[str] = None,
        settings: Optional[dict[str, Any]] = None,
        *,
        user_id: str,
        tenant_id: str,
    ) -> Session:
        """
        Create a new conversation session owned by user_id
        """
        session_settings = settings or {}
        if edition:
            session_settings["edition"] = edition

        async with db.session() as s:
            session = Session(
                title=title, settings=session_settings, user_id=user_id, tenant_id=tenant_id, meta_data={}
            )
            s.add(session)
            await s.flush()
            await s.refresh(session)
            logger.info(f"Created session {session.id} for {user_id}: {title}")

        # ! Written after the transaction closes, because an object store cannot be rolled back with it
        meta.write_meta(
            session_meta_key(tenant_id, user_id, str(session.id)),
            meta.session_meta_payload(
                session_id=str(session.id),
                tenant_id=tenant_id,
                user_id=user_id,
                created_at=session.created_at,
            ),
        )
        return session

    async def get_session(self, session_id: UUID, *, user_id: str) -> Optional[Session]:
        """
        Get a session by ID, scoped to its owner (excludes soft-deleted)
        """
        async with db.session() as s:
            result = await s.execute(
                select(Session).where(
                    Session.id == session_id,
                    Session.deleted_at.is_(None),
                    *_owned(user_id),
                )
            )
            return result.scalar_one_or_none()

    async def get_session_with_messages(
        self,
        session_id: UUID,
        *,
        user_id: str,
        message_limit: int = 100,
    ) -> Optional[Session]:
        """
        Get a session with its messages eagerly loaded, scoped to its owner
        """
        async with db.session() as s:
            result = await s.execute(
                select(Session)
                .options(selectinload(Session.messages).selectinload(Message.feedback))
                .where(
                    Session.id == session_id,
                    Session.deleted_at.is_(None),
                    *_owned(user_id),
                )
            )
            session = result.scalar_one_or_none()
            if session and session.messages:
                session.messages.sort(key=lambda m: m.sequence_number)
                if len(session.messages) > message_limit:
                    session.messages = session.messages[-message_limit:]
            return session

    async def list_sessions(self, *, user_id: str, limit: int = 50, offset: int = 0) -> list[Session]:
        """
        List a user's active sessions, most recently updated first
        """
        async with db.session() as s:
            query = (
                select(Session)
                .where(Session.deleted_at.is_(None), *_owned(user_id))
                .order_by(Session.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await s.execute(query)
            return list(result.scalars().all())

    async def update_session(
        self,
        session_id: UUID,
        *,
        user_id: str,
        **kwargs: Any,
    ) -> Optional[Session]:
        """
        Update session fields (title, settings, meta_data), scoped to its owner
        """
        allowed = {"title", "settings", "meta_data"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}

        if not updates:
            return await self.get_session(session_id, user_id=user_id)

        async with db.session() as s:
            await s.execute(
                update(Session)
                .where(Session.id == session_id, Session.deleted_at.is_(None), *_owned(user_id))
                .values(**updates, updated_at=datetime.now(timezone.utc))
            )
            # ! The re-select needs the predicate too, or a non-owner reads the row back unchanged
            result = await s.execute(select(Session).where(Session.id == session_id, *_owned(user_id)))
            return result.scalar_one_or_none()

    async def delete_session(self, session_id: UUID, *, user_id: str) -> bool:
        """
        Soft-delete a session owned by user_id
        """
        async with db.session() as s:
            result = cast(
                CursorResult[Any],
                await s.execute(
                    update(Session)
                    .where(Session.id == session_id, Session.deleted_at.is_(None), *_owned(user_id))
                    .values(deleted_at=datetime.now(timezone.utc))
                ),
            )
            deleted = result.rowcount > 0
            if deleted:
                logger.info(f"Soft-deleted session {session_id}")
            return deleted

    # * Messages
    async def add_message(
        self,
        session_id: UUID,
        role: str,
        content: dict[str, Any],
        *,
        user_id: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        latency_ms: Optional[int] = None,
        stop_reason: Optional[str] = None,
        meta_data: Optional[dict[str, Any]] = None,
    ) -> Message:
        """
        Append a message to an active session the caller owns

        Raises LookupError for a foreign or soft-deleted session, so nothing is written into it
        The sequence number is one past the session's current maximum
        """
        async with db.session() as s:
            # ! The row lock also serializes concurrent appends, so two turns never take the same sequence number
            owned = await s.execute(
                select(Session.id)
                .where(Session.id == session_id, Session.deleted_at.is_(None), *_owned(user_id))
                .with_for_update()
            )
            if owned.scalar_one_or_none() is None:
                raise LookupError(f"Session {session_id} not found")

            result = await s.execute(
                select(func.coalesce(func.max(Message.sequence_number), 0)).where(Message.session_id == session_id)
            )
            next_seq = result.scalar_one() + 1

            message = Message(
                session_id=session_id,
                role=role,
                content=content,
                sequence_number=next_seq,
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=latency_ms,
                stop_reason=stop_reason,
                meta_data=meta_data or {},
            )
            s.add(message)
            await s.flush()
            await s.refresh(message)

            await s.execute(
                update(Session).where(Session.id == session_id).values(updated_at=datetime.now(timezone.utc))
            )

            return message

    async def get_messages(
        self,
        session_id: UUID,
        *,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Message]:
        """
        Get messages for a session the caller owns, ordered by sequence number
        """
        # ! Ownership gate first: a foreign session id returns nothing, not another user's messages
        if await self.get_session(session_id, user_id=user_id) is None:
            return []

        async with db.session() as s:
            result = await s.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.sequence_number.asc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def get_conversation_history(self, session_id: UUID, *, user_id: str) -> list[dict[str, Any]]:
        """
        The latest turns of a session the caller owns, oldest first, formatted for the model

        Bounded by settings.history_max_messages and settings.history_max_chars
        """
        # ! A foreign session id reads as empty, never as someone else's turns
        if await self.get_session(session_id, user_id=user_id) is None:
            return []
        async with db.session() as s:
            result = await s.execute(
                select(Message)
                .where(Message.session_id == session_id, Message.role.in_(("user", "assistant")))
                .order_by(Message.sequence_number.desc())
                .limit(settings.history_max_messages)
            )
            newest_first = list(result.scalars().all())
        return _history_window(newest_first, max_chars=settings.history_max_chars)

    # * Stats
    async def get_session_count(self, *, user_id: str) -> int:
        """
        Count a user's active sessions
        """
        async with db.session() as s:
            query = select(func.count(Session.id)).where(Session.deleted_at.is_(None), *_owned(user_id))
            result = await s.execute(query)
            return result.scalar_one()

    async def get_message_count(self, session_id: UUID) -> int:
        """Count messages in a session."""
        async with db.session() as s:
            result = await s.execute(select(func.count(Message.id)).where(Message.session_id == session_id))
            return result.scalar_one()


# * Global instance
session_service = SessionService()
