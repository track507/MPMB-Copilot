"""
Auto-title generator for new sessions

When a session lands its first user/assistant exchange, generate a short 4-6 word title from the user's first message
Mirrors what Claude web does

Designed to be called from a background asyncio task - never blocks the streaming response
Failures fall back to a truncated user message
"""

from uuid import UUID

from app.core.agent import generate as agent_generate
from app.logger import get_logger
from app.services.db.session_service import session_service

logger = get_logger(__name__)

_TITLE_INSTRUCTIONS = (
    "You generate concise titles for chat conversations. "
    "Given the user's first message, return a 4-6 word title that captures "
    "the topic. Do not use quotes, trailing punctuation, or the word 'chat'. "
    "Return only the title text — no preamble, no markdown."
)

_MAX_TITLE_CHARS = 80
_FALLBACK_TRUNCATE = 60


def _fallback_title(user_message: str) -> str:
    """
    Truncate the user message as a fallback when LLM call fails
    """
    cleaned = " ".join(user_message.strip().split())
    if len(cleaned) <= _FALLBACK_TRUNCATE:
        return cleaned or "New Conversation"
    return cleaned[:_FALLBACK_TRUNCATE].rstrip() + "…"


def _sanitize(title: str) -> str:
    """
    Strip whitespace, quotes, and trailing punctuation; cap length
    """
    cleaned = title.strip().strip("\"'`")
    cleaned = cleaned.rstrip(".!?,;:")
    if len(cleaned) > _MAX_TITLE_CHARS:
        cleaned = cleaned[:_MAX_TITLE_CHARS].rstrip() + "…"
    return cleaned


async def generate_session_title(session_id: UUID, user_message: str) -> None:
    """
    Generate and persist a session title from the first user message

    Runs in a background task; logs and swallows errors so a failure here cannot break the chat response that already finished streaming
    """
    try:
        response = await agent_generate(
            instructions=_TITLE_INSTRUCTIONS,
            user_prompt=user_message,
            temperature=0.3,
            max_tokens=32,
        )
        title = _sanitize(response.content)
        if not title:
            title = _fallback_title(user_message)
    except Exception as e:
        logger.warning(f"Title generation failed, using fallback: {e}")
        title = _fallback_title(user_message)

    try:
        await session_service.update_session(session_id, title=title)
        logger.info(f"Session {session_id} titled: {title!r}")
    except Exception as e:
        logger.error(f"Failed to update session title for {session_id}: {e}")
