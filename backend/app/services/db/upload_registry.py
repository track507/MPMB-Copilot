"""
Uploade registry: DB ops for the files table

Rows are the SoT for ownership, scope, and content hash
Bytes live on disk under config.upload_dir - UploadService owns that side
Nothing in this module touches the fs
"""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.logger import get_logger
from app.model.orm import File
from app.services.db.connection import db

logger = get_logger(__name__)


def _scope_filters(scope: str, owner_user_id: Optional[str], session_id: Optional[UUID]) -> list:
    """WHERE clauses identifying one scope target (a session, a user's library, or shared)."""
    filters = [File.scope == scope]
    if scope == "session":
        filters.append(File.session_id == session_id)
    elif scope == "global":
        filters.append(File.owner_user_id == owner_user_id)
    return filters


class UploadRegistry:
    """Persistence for uploaded-file rows."""

    async def upsert_file(
        self,
        *,
        scope: str,
        filename: str,
        original_filename: str,
        file_path: str,
        content_type: str,
        file_size: int,
        file_hash: str,
        owner_user_id: str,
        session_id: Optional[UUID] = None,
    ) -> File:
        # * Conflict target is the partial unique index for the scope
        if scope == "session":
            conflict: dict[str, Any] = {
                "index_elements": ["session_id", "filename"],
                "index_where": text("scope = 'session'"),
            }
        elif scope == "global":
            conflict = {
                "index_elements": ["owner_user_id", "filename"],
                "index_where": text("scope = 'global'"),
            }
        else:
            conflict = {"index_elements": ["filename"], "index_where": text("scope = 'shared'")}

        stmt = (
            insert(File)
            .values(
                scope=scope,
                filename=filename,
                original_filename=original_filename,
                file_path=file_path,
                content_type=content_type,
                file_size=file_size,
                file_hash=file_hash,
                owner_user_id=owner_user_id,
                session_id=session_id,
                meta_data={},
            )
            .on_conflict_do_update(
                **conflict,
                set_={
                    "original_filename": original_filename,
                    "content_type": content_type,
                    "file_size": file_size,
                    "file_hash": file_hash,
                    "uploaded_at": func.now(),
                    # ? Re-upload resets metadata, which also clears a stale missing flag
                    "meta_data": {},
                },
            )
            .returning(File)
        )
        async with db.session() as s:
            result = await s.execute(stmt)
            row = result.scalar_one()
            logger.info(f"Upserted upload {row.id}: {scope}/{filename}")
            return row

    async def get_file(self, file_id: UUID) -> Optional[File]:
        async with db.session() as s:
            return await s.get(File, file_id)

    async def get_by_name(
        self,
        *,
        scope: str,
        filename: str,
        owner_user_id: Optional[str] = None,
        session_id: Optional[UUID] = None,
    ) -> Optional[File]:
        async with db.session() as s:
            result = await s.execute(
                select(File).where(*_scope_filters(scope, owner_user_id, session_id), File.filename == filename)
            )
            return result.scalar_one_or_none()

    async def list_files(
        self, *, scope: str, owner_user_id: Optional[str] = None, session_id: Optional[UUID] = None
    ) -> list[File]:
        async with db.session() as s:
            result = await s.execute(
                select(File).where(*_scope_filters(scope, owner_user_id, session_id)).order_by(File.filename)
            )
            return list(result.scalars().all())

    async def count_files(
        self, *, scope: str, owner_user_id: Optional[str] = None, session_id: Optional[UUID] = None
    ) -> int:
        async with db.session() as s:
            result = await s.execute(
                select(func.count()).select_from(File).where(*_scope_filters(scope, owner_user_id, session_id))
            )
            return int(result.scalar_one())

    async def delete_file(self, file_id: UUID) -> bool:
        async with db.session() as s:
            result = await s.execute(delete(File).where(File.id == file_id))
            return result.rowcount > 0

    async def link_message(self, *, message_id: UUID, file_ids: list[UUID], session_id: UUID) -> int:
        """Stamp message_id onto rows - only rows that belong to that session link."""
        if not file_ids:
            return 0
        async with db.session() as s:
            result = await s.execute(
                update(File)
                .where(File.id.in_(file_ids), File.scope == "session", File.session_id == session_id)
                .values(message_id=message_id)
            )
            return result.rowcount

    async def mark_missing(self, file_id: UUID) -> None:
        async with db.session() as s:
            row = await s.get(File, file_id)
            if row is not None:
                row.meta_data = {**(row.meta_data or {}), "missing": True}


upload_registry = UploadRegistry()
