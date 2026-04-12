"""Tests for the stored-history -> PydanticAI message converter."""

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from app.services.llm.messages import to_pydantic_messages


def test_empty_history_returns_empty_list():
    assert to_pydantic_messages([]) == []


def test_single_user_message():
    result = to_pydantic_messages([{"role": "user", "content": "hello"}])

    assert len(result) == 1
    assert isinstance(result[0], ModelRequest)
    assert len(result[0].parts) == 1
    assert isinstance(result[0].parts[0], UserPromptPart)
    assert result[0].parts[0].content == "hello"


def test_single_assistant_message():
    result = to_pydantic_messages([{"role": "assistant", "content": "hi back"}])

    assert len(result) == 1
    assert isinstance(result[0], ModelResponse)
    assert len(result[0].parts) == 1
    assert isinstance(result[0].parts[0], TextPart)
    assert result[0].parts[0].content == "hi back"


def test_alternating_conversation_order_preserved():
    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]
    result = to_pydantic_messages(history)

    assert len(result) == 4
    assert isinstance(result[0], ModelRequest)
    assert isinstance(result[1], ModelResponse)
    assert isinstance(result[2], ModelRequest)
    assert isinstance(result[3], ModelResponse)
    assert result[0].parts[0].content == "q1"
    assert result[1].parts[0].content == "a1"
    assert result[2].parts[0].content == "q2"
    assert result[3].parts[0].content == "a2"


def test_system_role_is_dropped():
    history = [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "hi"},
    ]
    result = to_pydantic_messages(history)

    assert len(result) == 1
    assert isinstance(result[0], ModelRequest)
    assert result[0].parts[0].content == "hi"


def test_unknown_role_is_dropped():
    history = [
        {"role": "function", "content": "tool result"},
        {"role": "user", "content": "real message"},
    ]
    result = to_pydantic_messages(history)

    assert len(result) == 1
    assert isinstance(result[0], ModelRequest)
    assert result[0].parts[0].content == "real message"


def test_missing_content_defaults_to_empty_string():
    result = to_pydantic_messages([{"role": "user"}])

    assert len(result) == 1
    assert result[0].parts[0].content == ""


def test_consecutive_same_role_messages_preserved():
    """Don't merge - persistence layer decides ordering."""
    history = [
        {"role": "user", "content": "q1"},
        {"role": "user", "content": "q2"},
    ]
    result = to_pydantic_messages(history)

    assert len(result) == 2
    assert all(isinstance(m, ModelRequest) for m in result)
