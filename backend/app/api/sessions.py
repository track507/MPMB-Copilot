"""Session management API endpoints.

Provides CRUD operations for conversation sessions and
access to message history within sessions.

Endpoints:
    GET    /sessions              - List sessions
    POST   /sessions              - Create session
    GET    /sessions/{id}         - Get session with messages
    PUT    /sessions/{id}         - Update session
    DELETE /sessions/{id}         - Soft delete session
    GET    /sessions/{id}/messages - Get messages (paginated)
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.logger import get_logger
from app.model.schemas.session import (
    FeedbackOut,
    FeedbackUpsert,
    MessageOut,
    SessionCreate,
    SessionDetailOut,
    SessionListOut,
    SessionOut,
    SessionUpdate,
)
from app.services.db import db, feedback_service, session_service

logger = get_logger(__name__)
router = APIRouter()


def _require_db() -> None:
    """Raise 503 if the database is not connected."""
    if not db.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available",
        )


# * List sessions
@router.get(
    "/sessions",
    response_model=SessionListOut,
    summary="List Sessions",
    description="List conversation sessions, most recently updated first",
)
async def list_sessions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    _require_db()

    sessions = await session_service.list_sessions(limit=limit, offset=offset)
    total = await session_service.get_session_count()

    session_list = []
    for s in sessions:
        msg_count = await session_service.get_message_count(s.id)
        session_list.append(
            SessionOut(
                id=s.id,
                title=s.title,
                created_at=s.created_at,
                updated_at=s.updated_at,
                user_id=s.user_id,
                settings=s.settings or {},
                meta_data=s.meta_data or {},
                message_count=msg_count,
            )
        )

    return SessionListOut(
        sessions=session_list,
        total=total,
        limit=limit,
        offset=offset,
    )


# * Create session
@router.post(
    "/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create Session",
    description="Create a new conversation session",
)
async def create_session(body: SessionCreate):
    _require_db()

    session = await session_service.create_session(
        title=body.title,
        edition=body.edition,
        settings=body.settings,
    )

    return SessionOut(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        user_id=session.user_id,
        settings=session.settings or {},
        meta_data=session.meta_data or {},
        message_count=0,
    )


# * Get session with messages
@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetailOut,
    summary="Get Session",
    description="Get a session with its messages",
)
async def get_session(session_id: UUID):
    _require_db()

    session = await session_service.get_session_with_messages(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    messages = [MessageOut.model_validate(m) for m in (session.messages or [])]

    return SessionDetailOut(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        user_id=session.user_id,
        settings=session.settings or {},
        meta_data=session.meta_data or {},
        message_count=len(messages),
        messages=messages,
    )


# * Update session
@router.put(
    "/sessions/{session_id}",
    response_model=SessionOut,
    summary="Update Session",
    description="Update session title, settings, or metadata",
)
async def update_session(session_id: UUID, body: SessionUpdate):
    _require_db()

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    session = await session_service.update_session(session_id, **updates)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    msg_count = await session_service.get_message_count(session_id)

    return SessionOut(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        user_id=session.user_id,
        settings=session.settings or {},
        meta_data=session.meta_data or {},
        message_count=msg_count,
    )


# * Delete session
@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Session",
    description="Soft-delete a session",
)
async def delete_session(session_id: UUID):
    _require_db()

    deleted = await session_service.delete_session(session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )


# * Get messages
@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[MessageOut],
    summary="Get Messages",
    description="Get messages for a session (paginated)",
)
async def get_messages(
    session_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    _require_db()

    # Verify session exists
    session = await session_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    messages = await session_service.get_messages(
        session_id,
        limit=limit,
        offset=offset,
    )
    return [MessageOut.model_validate(m) for m in messages]


# * Set/replace feedback on an assistant message
@router.put(
    "/sessions/{session_id}/messages/{message_id}/feedback",
    response_model=FeedbackOut,
    summary="Set Message Feedback",
    description="Upsert thumbs up/down (+ optional note) on an assistant message",
)
async def set_message_feedback(session_id: UUID, message_id: UUID, body: FeedbackUpsert):
    _require_db()

    message = await feedback_service.get_message(message_id)
    if message is None or message.session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message {message_id} not found",
        )
    if message.role != "assistant":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feedback is only allowed on assistant messages",
        )

    feedback = await feedback_service.set_feedback(message_id, body.rating, body.note)
    return FeedbackOut.model_validate(feedback)


# * Clear feedback
@router.delete(
    "/sessions/{session_id}/messages/{message_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear Message Feedback",
    description="Remove any feedback vote on a message",
)
async def clear_message_feedback(session_id: UUID, message_id: UUID):
    _require_db()
    await feedback_service.clear_feedback(message_id)
