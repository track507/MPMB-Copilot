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

import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.config import config
from app.core.rag_engine import rag_engine
from app.logger import get_logger
from app.model.schemas.chat import ChatRequest, ChatResponse, ChatStreamChunk
from app.services.db import db, session_service
from app.services.title_generator import generate_session_title
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


async def _save_user_message(session_uuid: UUID | None, user_message: str) -> None:
    """
    Save the user message and trigger title generation on the first message

    Persisted before streaming begins so the message survives any downstream failure (e.g., agent request_limit or model errors)
    """
    if not session_uuid or not db.is_connected:
        return

    try:
        user_msg = await session_service.add_message(
            session_id=session_uuid,
            role="user",
            content={"text": user_message},
        )

        # ? First user message in a new session - kick off async title generation
        if user_msg.sequence_number == 1:
            asyncio.create_task(generate_session_title(session_uuid, user_message))
    except Exception as e:
        logger.error(f"Failed to save user message: {e}")


async def _save_assistant_message(
    session_uuid: UUID | None,
    assistant_content: str,
    rag_response=None,
    error: str | None = None,
) -> None:
    """Save the assistant message. Records partial content + error when the stream fails."""
    if not session_uuid or not db.is_connected:
        return

    try:
        kwargs: dict[str, Any] = {}
        meta_data: dict[str, Any] = {}

        if rag_response:
            usage = rag_response.usage if isinstance(rag_response.usage, dict) else {}
            timing = rag_response.timing if hasattr(rag_response, "timing") else {}
            tools_meta = getattr(rag_response, "tools", None)
            meta_data = {
                "timing": timing,
            }
            if usage:
                meta_data["usage"] = usage
            if tools_meta:
                meta_data["tools"] = tools_meta
            retrieval = getattr(rag_response, "retrieval", None)
            if retrieval:
                meta_data["retrieval"] = retrieval
            kwargs.update(
                provider=getattr(rag_response, "provider", None),
                model=getattr(rag_response, "model", None),
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                latency_ms=int(timing.get("total_ms", 0)) if isinstance(timing, dict) else 0,
                stop_reason=getattr(rag_response, "stop_reason", None),
            )

        if error:
            meta_data["error"] = error
            kwargs["stop_reason"] = "error"

        if meta_data:
            kwargs["meta_data"] = meta_data

        assistant_content_dict: dict[str, Any] = {"text": assistant_content}

        await session_service.add_message(
            session_id=session_uuid,
            role="assistant",
            content=assistant_content_dict,
            **kwargs,
        )
    except Exception as e:
        logger.error(f"Failed to save assistant message: {e}")


def _build_metadata(
    session_id: str = "",
    provider: str = "",
    model: str = "",
    usage: dict | None = None,
    timing: dict | None = None,
    tools: dict | None = None,
    retrieval: list | None = None,
    stop_reason: str | None = None,
) -> dict:
    """
    Build nested metadata matching the frontend `ChatMetadata` type

    `retrieval` is the per-turn agentic trace (one citation entry per mpmb_search call), included only when the turn searched
    """
    meta = {
        "session_id": session_id,
        "provider": provider,
        "model": model,
        "usage": usage or {},
        "timing": timing or {},
    }
    if tools:
        meta["tools"] = tools
    if retrieval:
        meta["retrieval"] = retrieval
    if stop_reason:
        meta["stop_reason"] = stop_reason
    return meta


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

        session_id = str(session_uuid) if session_uuid else (request.session_id or "")

        # * Persist user message before generation so it survives downstream failures
        await _save_user_message(session_uuid, request.message)

        try:
            rag_response = await rag_engine.generate(
                query=request.message,
                conversation_history=history,
                session_id=session_id,
                edition=request.edition or settings.default_edition,
                provider=request.provider,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
        except Exception as gen_error:
            await _save_assistant_message(session_uuid, "", error=str(gen_error))
            raise

        await _save_assistant_message(session_uuid, rag_response.content, rag_response)

        metadata = _build_metadata(
            session_id=session_id,
            provider=rag_response.provider,
            model=rag_response.model,
            usage=rag_response.usage,
            timing=rag_response.timing,
            retrieval=rag_response.retrieval,
        )

        return ChatResponse(
            response=rag_response.content,
            session_id=session_id,
            sources=None,
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

        # * Persist user message before streaming so it survives any agent/model failure
        await _save_user_message(session_uuid, request.message)

        async def event_generator():
            """Generate SSE events from the RAG stream."""
            full_content = []
            final_event = None

            try:
                async for event in rag_engine.stream(
                    query=request.message,
                    conversation_history=history,
                    session_id=session_id,
                    edition=request.edition or settings.default_edition,
                    provider=request.provider,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                ):
                    if event.done:
                        final_event = event
                        assistant_text = "".join(full_content)
                        await _save_assistant_message(session_uuid, assistant_text, final_event)
                        final_chunk = ChatStreamChunk(
                            chunk="",
                            done=True,
                            metadata=_build_metadata(
                                session_id=session_id,
                                provider=event.provider or "",
                                model=event.model or "",
                                usage=event.usage,
                                timing=event.timing,
                                tools=event.tools,
                                stop_reason=event.stop_reason,
                                retrieval=event.retrieval,
                            ),
                        )
                        yield f"data: {final_chunk.model_dump_json()}\n\n"
                        yield "data: [DONE]\n\n"
                    elif event.event in ("tool_start", "tool_end"):
                        tool_chunk = ChatStreamChunk(
                            chunk="",
                            done=False,
                            event=event.event,
                            tool=event.tool,
                        )
                        yield f"data: {tool_chunk.model_dump_json(exclude_none=True)}\n\n"
                    else:
                        full_content.append(event.content)
                        chunk = ChatStreamChunk(
                            chunk=event.content,
                            done=False,
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

            except Exception as e:
                logger.error(f"Stream error: {e}", exc_info=True)
                # ! Persist partial text + error so the user's question survives the page reload
                partial_text = "".join(full_content)
                await _save_assistant_message(session_uuid, partial_text, error=str(e))
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
