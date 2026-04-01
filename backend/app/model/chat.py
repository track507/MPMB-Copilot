from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Chat request model for the /chat endpoint.

    Represents a user's chat message along with optional parameters for
    conversation context and LLM generation settings.

    Attributes:
            message: User's input message (1-10000 chars)
            conversation_id: Optional UUID to continue existing conversation
            provider: LLM provider selection (anthropic/openai/ollama)
            model: Specific model override (e.g., 'claude-sonnet-4-5')
            temperature: Controls randomness (0.0=deterministic, 2.0=creative)
            max_tokens: Maximum length of generated response (1-8000 tokens)
            include_source: Whether to include MPMB source code references in response

    Example:
            >>> request = ChatRequest(
            ...     message="How do I add a custom spell?",
            ...     provider="anthropic",
            ...     temperature=0.2,
            ...     include_source=True
            ... )
    """

    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")
    provider: Optional[str] = Field(None, description="LLM provider (anthropic/openai/ollama)")
    model: Optional[str] = Field(None, description="Specific model to use")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Temperature for generation")
    max_tokens: Optional[int] = Field(None, gt=0, le=8000, description="Maximum tokens to generate")
    include_source: bool = Field(True, description="Include source code references")
    edition: Optional[str] = Field(None, description="D&D edition (2014/2024)")


class ChatResponse(BaseModel):
    """Chat response model returned from the /chat endpoint.

    Contains the assistant's response along with conversation tracking,
    source references, and metadata about the generation process.

    Attributes:
            response: The assistant's generated response text
            conversation_id: UUID of the conversation (created if not provided in request)
            sources: Optional list of source code references used to generate response.
                    Each dict contains:
                    - file: source file path
                    - content: relevant code snippet
                    - score: similarity/relevance score
                    - line_range: tuple of (start_line, end_line)
            metadata: Generation metadata including:
                    - provider: LLM provider used
                    - model: Specific model used
                    - prompt_tokens: Tokens in the prompt
                    - completion_tokens: Tokens in the response
                    - total_tokens: Total tokens used
                    - latency_ms: Response generation time
                    - retrieval_time_ms: Time spent retrieving context
                    - chunks_retrieved: Number of code chunks used

    Example:
            >>> response = ChatResponse(
            ...     response="To add a spell, use SpellsList...",
            ...     conversation_id="550e8400-e29b-41d4-a716-446655440000",
            ...     sources=[{"file": "spells.js", "score": 0.89, ...}],
            ...     metadata={"model": "claude-sonnet-4-5", "total_tokens": 1250}
            ... )
    """

    response: str = Field(..., description="Assistant's generated response")
    conversation_id: str = Field(..., description="Conversation UUID")
    sources: Optional[list[dict]] = Field(None, description="List of source code references used in generation")
    metadata: dict = Field(..., description="Generation metadata (model, tokens, timing, retrieval info)")


class ChatStreamChunk(BaseModel):
    """Individual chunk from a streaming chat response.

    Used for server-sent events (SSE) streaming to provide real-time
    response generation to clients.

    Attributes:
            chunk: Partial response text for this stream chunk
            done: Whether this is the final chunk in the stream
            metadata: Optional metadata sent with final chunk, same structure as
                    ChatResponse.metadata. Only present when done=True.

    Example:
            >>> # Intermediate chunk
            >>> chunk = ChatStreamChunk(chunk="To add a spell", done=False)
            >>>
            >>> # Final chunk
            >>> final = ChatStreamChunk(
            ...     chunk="",
            ...     done=True,
            ...     metadata={"total_tokens": 1250, "latency_ms": 2340}
            ... )
    """

    chunk: str = Field(..., description="Partial response text")
    done: bool = Field(False, description="Whether stream is complete")
    metadata: Optional[dict] = Field(None, description="Generation metadata (only in final chunk when done=True)")
