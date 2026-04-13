"""Chat endpoint for RAG-powered conversations.

Full pipeline:
    request -> session load -> rag_engine -> retriever -> prompts -> LLM -> session save -> response

Supports both complete responses (POST /chat) and streaming via
Server-Sent Events (POST /chat/stream).

Session persistence:
    - If session_id is provided, loads conversation history from PostgreSQL
    - If session_id is omitted, creates a new session automatically
    - User and assistant messages are saved after each exchange
    - Falls back to stateless mode if the database is unavailable
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.config import config
from app.core.rag_engine import rag_engine
from app.logger import get_logger
from app.model.schemas.chat import ChatRequest, ChatResponse, ChatStreamChunk
from app.services.db import db, session_service
from app.settings import settings

logger = get_logger(__name__)
router = APIRouter()


# * Helpers
async def _load_history(session_id_str: str | None) -> tuple[UUID | None, list[dict]]:
    """Load conversation history from the session store.

    Returns (resolved_session_uuid, history_list).
    If DB is unavailable or session_id is None, returns (None, []).
    """
    if not session_id_str or not db.is_connected:
        return None, []

    try:
        session_uuid = UUID(session_id_str)
        history = await session_service.get_conversation_history(session_uuid)
        return session_uuid, history
    except (ValueError, Exception) as e:
        logger.warning(f"Failed to load session history: {e}")
        return None, []


async def _ensure_session(session_uuid: UUID | None, edition: str | None) -> UUID | None:
    """Ensure a session exists. Creates one if needed and DB is available."""
    if not db.is_connected:
        return None

    if session_uuid:
        return session_uuid

    try:
        session = await session_service.create_session(
            title="New Conversation",
            edition=edition,
        )
        return session.id
    except Exception as e:
        logger.warning(f"Failed to create session: {e}")
        return None


async def _save_messages(
    session_uuid: UUID | None,
    user_message: str,
    assistant_content: str,
    rag_response=None,
) -> None:
    """Save user and assistant messages to the session."""
    if not session_uuid or not db.is_connected:
        return

    try:
        await session_service.add_message(
            session_id=session_uuid,
            role="user",
            content={"text": user_message},
        )

        kwargs = {}
        if rag_response:
            usage = rag_response.usage if isinstance(rag_response.usage, dict) else {}
            timing = rag_response.timing if hasattr(rag_response, "timing") else {}
            kwargs.update(
                provider=getattr(rag_response, "provider", None),
                model=getattr(rag_response, "model", None),
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                latency_ms=int(timing.get("total_ms", 0)) if isinstance(timing, dict) else 0,
                stop_reason=getattr(rag_response, "stop_reason", None),
                meta_data={
                    "retrieval": getattr(rag_response, "retrieval_info", None),
                    "timing": timing,
                },
            )

        await session_service.add_message(
            session_id=session_uuid,
            role="assistant",
            content={"text": assistant_content},
            **kwargs,
        )
    except Exception as e:
        logger.error(f"Failed to save messages: {e}")


def _build_metadata(
    session_id: str = "",
    provider: str = "",
    model: str = "",
    usage: dict | None = None,
    retrieval_info: dict | None = None,
    timing: dict | None = None,
) -> dict:
    """Build nested metadata matching the frontend `ChatMetadata` type.

    Groups are passed through as-is so Phase B can add `tool_events`
    without another metadata refactor.
    """
    return {
        "session_id": session_id,
        "provider": provider,
        "model": model,
        "usage": usage or {},
        "retrieval": retrieval_info or {},
        "timing": timing or {},
    }


def _build_sources_from_rag(rag_response) -> list[dict]:
    """Extract source citations from a RAG response."""
    sources = []
    retrieval = rag_response.retrieval_info or {}

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


# * POST /chat - complete response
@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with RAG",
    description="Send a message and receive AI-generated MPMB code assistance",
)
async def chat(request: ChatRequest):
    """Generate a complete RAG-powered response with session persistence."""
    try:
        logger.info(
            f"Chat request: session_id={request.session_id} provider={request.provider} edition={request.edition}"
        )

        session_uuid, history = await _load_history(request.session_id)
        session_uuid = await _ensure_session(session_uuid, request.edition)

        rag_response = await rag_engine.generate(
            query=request.message,
            conversation_history=history,
            edition=request.edition or settings.default_edition,
            provider=request.provider,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        await _save_messages(session_uuid, request.message, rag_response.content, rag_response)

        session_id = str(session_uuid) if session_uuid else (request.session_id or "")

        sources = None
        if request.include_source and rag_response.retrieval_info:
            sources = _build_sources_from_rag(rag_response)

        metadata = _build_metadata(
            session_id=session_id,
            provider=rag_response.provider,
            model=rag_response.model,
            usage=rag_response.usage,
            retrieval_info=rag_response.retrieval_info,
            timing=rag_response.timing,
        )

        return ChatResponse(
            response=rag_response.content,
            session_id=session_id,
            sources=sources,
            metadata=metadata,
        )

    except ValueError as e:
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
    """Stream a RAG-powered response via SSE with session persistence."""
    try:
        logger.info(
            f"Streaming chat request: session_id={request.session_id} provider={request.provider} edition={request.edition}"
        )

        session_uuid, history = await _load_history(request.session_id)
        session_uuid = await _ensure_session(session_uuid, request.edition)

        session_id = str(session_uuid) if session_uuid else (request.session_id or "")

        async def event_generator():
            """Generate SSE events from the RAG stream."""
            full_content = []
            final_event = None

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
                        final_event = event
                        final_chunk = ChatStreamChunk(
                            chunk="",
                            done=True,
                            metadata=_build_metadata(
                                session_id=session_id,
                                provider=event.provider or "",
                                model=event.model or "",
                                usage=event.usage,
                                retrieval_info=event.retrieval_info,
                                timing=event.timing,
                            ),
                        )
                        yield f"data: {final_chunk.model_dump_json()}\n\n"
                        yield "data: [DONE]\n\n"
                    else:
                        full_content.append(event.content)
                        chunk = ChatStreamChunk(
                            chunk=event.content,
                            done=False,
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

                assistant_text = "".join(full_content)
                await _save_messages(session_uuid, request.message, assistant_text, final_event)

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
                "X-Session-Id": session_id,
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
