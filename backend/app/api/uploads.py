"""
Scope file uploads: transport + storage only

Endpoints:
    POST   /uploads               - Upload into a scope (multipart)
    GET    /uploads               - List a scope
    GET    /uploads/{id}/content  - Download stored bytes
    DELETE /uploads/{id}          - Remove row + disk file
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import Principal, current_principal
from app.logger import get_logger
from app.model.orm import File
from app.model.schemas.upload import FileListOut, FileOut, UploadScope
from app.services.db import db, session_service
from app.services.uploads import UploadError, upload_service

logger = get_logger(__name__)
router = APIRouter()


def _require_db() -> None:
    if not db.is_connected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database not available")


def _http(exc: UploadError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _to_out(row: File) -> FileOut:
    return FileOut(
        id=row.id,
        scope=row.scope,
        session_id=row.session_id,
        filename=row.filename,
        original_filename=row.original_filename,
        file_size=row.file_size,
        content_type=row.content_type,
        file_hash=row.file_hash,
        uploaded_at=row.uploaded_at,
        message_id=row.message_id,
        missing=bool((row.meta_data or {}).get("missing", False)),
    )


# * Upload a file
@router.post(
    "/uploads",
    response_model=FileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload file",
    description="Upload a file into the session, global, or shared scope",
)
async def upload_file(
    file: UploadFile,
    scope: UploadScope = Form(...),
    session_id: Optional[UUID] = Form(None),
    principal: Principal = Depends(current_principal),
):
    _require_db()

    if scope is UploadScope.session and session_id is not None:
        if await session_service.get_session(session_id=session_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "not_found", "message": f"Session {session_id} not found"},
            )

    try:
        row = await upload_service.store(
            scope=scope.value, user_id=principal.user_id, role=principal.role, upload=file, session_id=session_id
        )
    except UploadError as e:
        raise _http(e)
    return _to_out(row=row)


# * List a scope
@router.get(
    "/uploads",
    response_model=FileListOut,
    summary="List Uploads",
    description="List uploaded files in a scope; rows whose bytes vanished are flagged missing",
)
async def list_uploads(
    scope: UploadScope,
    session_id: Optional[UUID] = None,
    principal: Principal = Depends(current_principal),
):
    _require_db()
    try:
        rows = await upload_service.list_with_reconcile(
            scope=scope.value,
            user_id=principal.user_id,
            role=principal.role,
            session_id=session_id,
        )
    except UploadError as e:
        raise _http(e)
    return FileListOut(files=[_to_out(r) for r in rows], total=len(rows))


# * Download stored bytes
@router.get(
    "/uploads/{file_id}/content",
    summary="Download Upload",
    description="Download the stored bytes of an uploaded file",
)
async def download_upload(file_id: UUID, principal: Principal = Depends(current_principal)):
    _require_db()
    try:
        path, row = await upload_service.open_content(file_id=file_id, user_id=principal.user_id, role=principal.role)
    except UploadError as e:
        raise _http(e)
    # ! attachment + nosniff: stored .js served inline would be a stored-XSS vector
    return FileResponse(
        path,
        filename=row.filename,
        media_type="application/octet-stream",
        headers={"X-Content-Type-Options": "nosniff"},
    )


# * Delete an upload
@router.delete(
    "/uploads/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Upload",
    description="Remove an uploaded file (row and disk content)",
)
async def delete_upload(file_id: UUID, principal: Principal = Depends(current_principal)):
    _require_db()
    try:
        await upload_service.delete(file_id=file_id, user_id=principal.user_id, role=principal.role)
    except UploadError as e:
        raise _http(e)
