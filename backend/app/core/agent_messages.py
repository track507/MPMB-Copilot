"""
Conversion between stored conversation history and PydanticAI messages

The session database stores history as plain dicts (services/db/session_service.py)
Each row is {"role": "user" or "assistant", "content": str}, while `Agent.run` takes typed parts
This module is the only boundary between the two shapes, so swapping frameworks again touches one file

System messages never travel through here
The static instructions and the per-turn prompt are arguments to the agent, not history entries
"""

from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from app.logger import get_logger

logger = get_logger(__name__)


def to_pydantic_messages(history: list[dict[str, Any]]) -> list[ModelMessage]:
    """
    Convert stored history dicts into the messages `Agent.run(message_history=...)` accepts

    An unknown role is dropped with a warning rather than raising, so one bad row cannot lose the turn
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
            # * Instructions are set on the agent, so a stored system row would be a second, staler copy
            logger.warning(
                "Dropping 'system' role from conversation history - "
                "system prompts are configured on the Agent, not per-turn"
            )
        else:
            logger.warning(f"Dropping message with unknown role: {role!r}")

    return messages
