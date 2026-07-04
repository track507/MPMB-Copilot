"""Session persistence service.

Handles CRUD for sessions and messages, plus retrieval tracking.
All operations use the async database pool from `database.py`.

Usage:
    from app.services.db import session_service

    session = await session_service.create_session(title="My Chat")
    msg = await session_service.add_message(session.id, "user", {"text": "Hello"})
    history = await session_service.get_messages(session.id)
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.logger import get_logger
from app.model.orm import Message, MessageRetrieval, Session
from app.services.db.connection import db

logger = get_logger(__name__)


class SessionService:
    """Session and message persistence."""

    # * Sessions
    async def create_session(
        self,
        title: str = "New Conversation",
        edition: Optional[str] = None,
        settings: Optional[dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Session:
        """Create a new conversation session."""
        session_settings = settings or {}
        if edition:
            session_settings["edition"] = edition

        async with db.session() as s:
            session = Session(
                title=title,
                settings=session_settings,
                user_id=user_id,
                meta_data={},
            )
            s.add(session)
            await s.flush()
            await s.refresh(session)
            logger.info(f"Created session {session.id}: {title}")
            return session

    async def get_session(self, session_id: UUID) -> Optional[Session]:
        """Get a session by ID (excludes soft-deleted)."""
        async with db.session() as s:
            result = await s.execute(
                select(Session).where(
                    Session.id == session_id,
                    Session.deleted_at.is_(None),
                )
            )
            return result.scalar_one_or_none()

    async def get_session_with_messages(
        self,
        session_id: UUID,
        message_limit: int = 100,
    ) -> Optional[Session]:
        """Get a session with its messages eagerly loaded."""
        async with db.session() as s:
            result = await s.execute(
                select(Session)
                .options(selectinload(Session.messages).selectinload(Message.feedback))
                .where(
                    Session.id == session_id,
                    Session.deleted_at.is_(None),
                )
            )
            session = result.scalar_one_or_none()
            if session and session.messages:
                session.messages.sort(key=lambda m: m.sequence_number)
                if len(session.messages) > message_limit:
                    session.messages = session.messages[-message_limit:]
            return session

    async def list_sessions(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Session]:
        """List active sessions, most recently updated first."""
        async with db.session() as s:
            query = (
                select(Session)
                .where(Session.deleted_at.is_(None))
                .order_by(Session.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            if user_id:
                query = query.where(Session.user_id == user_id)

            result = await s.execute(query)
            return list(result.scalars().all())

    async def update_session(
        self,
        session_id: UUID,
        **kwargs: Any,
    ) -> Optional[Session]:
        """Update session fields (title, settings, meta_data)."""
        allowed = {"title", "settings", "meta_data"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}

        if not updates:
            return await self.get_session(session_id)

        async with db.session() as s:
            await s.execute(
                update(Session)
                .where(Session.id == session_id, Session.deleted_at.is_(None))
                .values(**updates, updated_at=datetime.now(timezone.utc))
            )
            result = await s.execute(select(Session).where(Session.id == session_id))
            return result.scalar_one_or_none()

    async def delete_session(self, session_id: UUID) -> bool:
        """Soft-delete a session."""
        async with db.session() as s:
            result = await s.execute(
                update(Session)
                .where(Session.id == session_id, Session.deleted_at.is_(None))
                .values(deleted_at=datetime.now(timezone.utc))
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
        provider: Optional[str] = None,
        model: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        latency_ms: Optional[int] = None,
        stop_reason: Optional[str] = None,
        meta_data: Optional[dict[str, Any]] = None,
    ) -> Message:
        """Add a message to a session.

        Sequence number is auto-incremented based on the current max
        for the session.
        """
        async with db.session() as s:
            # Get next sequence number
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

            # Update session's updated_at
            await s.execute(
                update(Session).where(Session.id == session_id).values(updated_at=datetime.now(timezone.utc))
            )

            return message

    async def get_messages(
        self,
        session_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Message]:
        """Get messages for a session, ordered by sequence number."""
        async with db.session() as s:
            result = await s.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.sequence_number.asc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def get_conversation_history(
        self,
        session_id: UUID,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get conversation history formatted for the LLM context.

        Returns dicts with 'role' and 'content' keys, suitable for
        passing directly to the RAG engine.
        """
        messages = await self.get_messages(session_id, limit=limit)
        history = []
        for msg in messages:
            text = msg.content.get("text", "") if isinstance(msg.content, dict) else str(msg.content)
            if text and msg.role in ("user", "assistant"):
                history.append({"role": msg.role, "content": text})
        return history

    # ! Unpopulated: the chat path records retrieval on meta_data["retrieval"], not this table
    # * Retrieval Tracking
    async def track_retrievals(
        self,
        message_id: UUID,
        chunks: list[dict[str, Any]],
    ) -> list[MessageRetrieval]:
        """Record which document chunks were used for a message.

        Each dict in `chunks` should have:
            - document_chunk_id: UUID
            - rank: int
            - score: float
            - snippet: optional str
        """
        if not chunks:
            return []

        async with db.session() as s:
            retrievals = []
            for chunk_data in chunks:
                retrieval = MessageRetrieval(
                    message_id=message_id,
                    document_chunk_id=chunk_data["document_chunk_id"],
                    rank=chunk_data["rank"],
                    score=chunk_data["score"],
                    snippet=chunk_data.get("snippet"),
                )
                s.add(retrieval)
                retrievals.append(retrieval)

            await s.flush()
            for r in retrievals:
                await s.refresh(r)

            return retrievals

    # * Stats
    async def get_session_count(self, user_id: Optional[str] = None) -> int:
        """Count active (non-deleted) sessions."""
        async with db.session() as s:
            query = select(func.count(Session.id)).where(Session.deleted_at.is_(None))
            if user_id:
                query = query.where(Session.user_id == user_id)
            result = await s.execute(query)
            return result.scalar_one()

    async def get_message_count(self, session_id: UUID) -> int:
        """Count messages in a session."""
        async with db.session() as s:
            result = await s.execute(select(func.count(Message.id)).where(Message.session_id == session_id))
            return result.scalar_one()


# * Global instance
session_service = SessionService()
