"""Conversion between stored conversation history and PydanticAI messages.

The session DB stores conversation history as a list of plain dicts
``[{"role": "user"|"assistant", "content": str}, ...]`` (see
``session_service.get_conversation_history``).  PydanticAI's ``Agent.run``
expects ``message_history: list[ModelMessage]`` where each entry is a
``ModelRequest`` (user side) or ``ModelResponse`` (assistant side) wrapping
typed parts.

This module is the single boundary between the framework-agnostic stored
shape and PydanticAI's typed messages.  Keep it isolated from the LLM
client so that swapping frameworks again only touches this file.

System messages are NOT handled here - the static system prompt and
per-turn RAG context are passed via ``Agent(instructions=...)`` and the
user-prompt argument, not via message history.
"""

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from app.logger import get_logger

logger = get_logger(__name__)


def to_pydantic_messages(history: list[dict]) -> list[ModelMessage]:
    """Convert stored conversation history dicts to PydanticAI messages.

    Args:
        history: Stored history shape - list of dicts each with
            ``role`` (``"user"`` or ``"assistant"``) and ``content`` (str).

    Returns:
        List of ``ModelMessage`` ready for ``Agent.run(message_history=...)``.
        Unknown roles are skipped with a warning.
    """
    messages: list[ModelMessage] = []

    for entry in history:
        role = entry.get("role")
        content = entry.get("content", "")

        if role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif role == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=content)]))
        elif role == "system":
            # System prompt is set on the Agent, not in message history.
            logger.warning(
                "Dropping 'system' role from conversation history - "
                "system prompts are configured on the Agent, not per-turn"
            )
        else:
            logger.warning(f"Dropping message with unknown role: {role!r}")

    return messages
