"""Chat endpoint for RAG-powered conversations.

Replaces the placeholder implementation with the full pipeline:
    request -> rag_engine -> retriever -> prompts -> LLM -> response

Supports both complete responses (POST /chat) and streaming via
Server-Sent Events (POST /chat/stream).

Session persistence (loading/saving conversation history from
PostgreSQL) is stubbed here and will be implemented in the session
service phase.  For now, each request is stateless - the frontend
can pass conversation_history in a future request body extension,
or we wire sessions when the DB layer is ready.
"""

import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.config import config
from app.core.rag_engine import rag_engine
from app.model.chat import ChatRequest, ChatResponse, ChatStreamChunk
from app.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# * Helpers
def _build_source_list(retrieval_info: dict, retrieval_result=None) -> list[dict]:
    """Build source citations from retrieval metadata.

    Returns a compact list of source references for the frontend to
    display as expandable citations.
    """
    sources = []

    # We need the actual chunk data, not just the summary.
    # The rag_engine returns retrieval_info (summary dict), but we need
    # the full chunks for source attribution.  For now, we reconstruct
    # from what's available.  Once session persistence lands, we'll
    # store and retrieve these properly.
    return sources


async def _load_conversation_history(conversation_id: str | None) -> list[dict]:
    """Load conversation history from session storage.

    TODO: Implement with session service (Phase 5).
    For now returns empty - each request is stateless.
    """
    if not conversation_id:
        return []

    # Placeholder: when session service exists, this becomes:
    # session = await session_service.get_session(conversation_id)
    # return [{"role": m.role, "content": m.content} for m in session.messages]
    return []


# * POST /chat - complete response
@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with RAG",
    description="Send a message and receive AI-generated MPMB code assistance",
)
async def chat(request: ChatRequest):
    """Generate a complete RAG-powered response.

    Pipeline:
    1. Load conversation history (from session, if provided)
    2. Retrieve relevant MPMB code chunks (tier-aware)
    3. Build prompt with static instructions + RAG context
    4. Generate LLM response (with prompt caching for Anthropic)
    5. Return response with metadata and source citations
    """
    try:
        logger.info(
            f"Chat request: conversation_id={request.conversation_id} "
            f"provider={request.provider} edition={request.edition}"
        )

        # Load conversation history
        history = await _load_conversation_history(request.conversation_id)

        # Run full RAG pipeline
        rag_response = await rag_engine.generate(
            query=request.message,
            conversation_history=history,
            edition=request.edition or settings.default_edition,
            provider=request.provider,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        # Build response
        conversation_id = request.conversation_id or str(uuid4())

        # Source citations (when include_source is True)
        sources = None
        if request.include_source and rag_response.retrieval_info:
            sources = _build_sources_from_rag(rag_response)

        metadata = {
            "provider": rag_response.provider,
            "model": rag_response.model,
            "usage": rag_response.usage,
            "stop_reason": rag_response.stop_reason,
            "retrieval": rag_response.retrieval_info,
            "timing": rag_response.timing,
        }

        return ChatResponse(
            response=rag_response.content,
            conversation_id=conversation_id,
            sources=sources,
            metadata=metadata,
        )

    except ValueError as e:
        # Config errors (missing API key, unknown provider)
        logger.error(f"Configuration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate response: {str(e)}"
            if config.is_development
            else "An error occurred while generating the response.",
        )


# * POST /chat/stream - streaming SSE response
@router.post(
    "/chat/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream Chat Response",
    description="Stream AI-generated responses via Server-Sent Events (SSE)",
)
async def chat_stream(request: ChatRequest):
    """Stream a RAG-powered response via SSE.

    Retrieval happens before streaming starts (the LLM needs context
    to generate).  Then LLM output streams token-by-token as SSE events.

    Event format:
        data: {"chunk": "partial text", "done": false}
        data: {"chunk": "", "done": true, "metadata": {...}}
        data: [DONE]
    """
    try:
        logger.info(
            f"Streaming chat request: conversation_id={request.conversation_id} "
            f"provider={request.provider} edition={request.edition}"
        )

        # Load conversation history
        history = await _load_conversation_history(request.conversation_id)

        conversation_id = request.conversation_id or str(uuid4())

        async def event_generator():
            """Generate SSE events from the RAG stream."""
            try:
                async for event in rag_engine.stream(
                    query=request.message,
                    conversation_history=history,
                    edition=request.edition or settings.default_edition,
                    provider=request.provider,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                ):
                    if event.done:
                        # Final event with metadata
                        final_chunk = ChatStreamChunk(
                            chunk="",
                            done=True,
                            metadata={
                                "conversation_id": conversation_id,
                                "usage": event.usage,
                                "retrieval": event.retrieval_info,
                                "timing": event.timing,
                            },
                        )
                        yield f"data: {final_chunk.model_dump_json()}\n\n"
                        yield "data: [DONE]\n\n"
                    else:
                        chunk = ChatStreamChunk(
                            chunk=event.content,
                            done=False,
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

            except Exception as e:
                logger.error(f"Stream error: {e}", exc_info=True)
                error_chunk = ChatStreamChunk(
                    chunk="",
                    done=True,
                    metadata={"error": str(e)},
                )
                yield f"data: {error_chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Conversation-Id": conversation_id,
            },
        )

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Chat stream endpoint error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start streaming: {str(e)}" if config.is_development else "An error occurred.",
        )


# * Source formatting
def _build_sources_from_rag(rag_response) -> list[dict]:
    """Extract source citations from a RAG response.

    Pulls file paths, line numbers, and relevance scores from the
    retrieval info for frontend display.
    """
    sources = []
    retrieval = rag_response.retrieval_info or {}

    # The retrieval_info from rag_engine is a summary dict.
    # For detailed source tracking, we'll add the actual chunk references
    # once session persistence stores them per-message.
    # For now, return summary counts so the frontend knows retrieval happened.

    auth_count = retrieval.get("authoritative_count", 0)
    ex_count = retrieval.get("examples_count", 0)

    if auth_count or ex_count:
        sources.append(
            {
                "type": "retrieval_summary",
                "authoritative_chunks": auth_count,
                "example_chunks": ex_count,
                "intent": retrieval.get("intent"),
                "edition": retrieval.get("edition"),
                "object_type": retrieval.get("object_type"),
            }
        )

    return sources
