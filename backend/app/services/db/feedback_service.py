"""Answer-feedback persistence (thumbs up/down + optional note on assistant messages)."""

from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select

from app.logger import get_logger
from app.model.orm import Message, MessageFeedback
from app.services.db.connection import db

logger = get_logger(__name__)


class FeedbackService:
    """
    Upsert / clear / read feedback for a single message
    """

    async def set_feedback(self, message_id: UUID, rating: str, note: Optional[str]) -> MessageFeedback:
        """Insert or update the one feedback row for a message."""
        async with db.session() as s:
            result = await s.execute(select(MessageFeedback).where(MessageFeedback.message_id == message_id))
            fb = result.scalar_one_or_none()
            if fb is None:
                fb = MessageFeedback(message_id=message_id, rating=rating, note=note)
                s.add(fb)
            else:
                fb.rating = rating
                fb.note = note
            await s.flush()
            await s.refresh(fb)
            return fb

    async def clear_feedback(self, message_id: UUID) -> bool:
        """
        Delete the feedback row for a message
        True if a row was removed
        """
        async with db.session() as s:
            result = await s.execute(delete(MessageFeedback).where(MessageFeedback.message_id == message_id))
            return result.rowcount > 0

    async def get_message(self, message_id: UUID) -> Optional[Message]:
        """
        Fetch a message for validation (existence, session, role)
        """
        async with db.session() as s:
            result = await s.execute(select(Message).where(Message.id == message_id))
            return result.scalar_one_or_none()


# * Global instance
feedback_service = FeedbackService()
