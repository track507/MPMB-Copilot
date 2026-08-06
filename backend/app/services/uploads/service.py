"""
Scoped upload storage: the single entry point for uploads

store() is the only place bytes land and the row commits
future post store steps (metadata JSON, indexing) plug in at the marked extension point
Takes user_id/role primitives, never Principal - services must never import app.api
"""

import hashlib
import os
import time
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from fastapi import UploadFile

from app.config import config
from app.logger import get_logger
from app.model.orm import File
from app.services.db import upload_registry
from app.services.uploads.errors import UploadError
from app.services.uploads.sanitize import sanitize_filename
from app.settings import settings

logger = get_logger(__name__)

_SCOPES = frozenset({"session", "global", "shared"})
_CHUNK_BYTES = 1024 * 1024
_TEMP_MAX_AGE_SECONDS = 24 * 3600


class UploadService:
    """
    Disk + Registry for uploads
    """

    def _scope_dir(self, *, scope: str, owner_user_id: str, session_id: Optional[UUID]) -> Path:
        base = Path(config.upload_dir)
        if scope == "session":
            return base / "session" / str(session_id)
        elif scope == "global":
            return base / "global" / owner_user_id
        return base / "shared"

    def _check_access(self, *, scope: str, row_owner: str, user_id: str, role: str, write: bool) -> None:
        if role == "admin":
            return
        if scope == "global" and row_owner != user_id:
            raise UploadError(403, "forbidden", "Not your file")
        if scope == "shared" and write:
            raise UploadError(403, "forbidden", "The shared library is admin-managed")

    def _registry_target(self, *, scope: str, user_id: str, session_id: Optional[UUID]) -> dict:
        """
        Filters identifying one scope target for count/get_by_name/list
        """
        if scope == "session":
            return {"scope": scope, "session_id": session_id}
        if scope == "global":
            return {"scope": scope, "owner_user_id": user_id}
        return {"scope": scope}

    async def store(
        self, *, scope: str, user_id: str, role: str, upload: UploadFile, session_id: Optional[UUID] = None
    ) -> File:
        if scope not in _SCOPES:
            raise UploadError(400, "invalid_scope", f"Unknown scope: {scope}")
        if (scope == "session") != (session_id is not None):
            raise UploadError(400, "invalid_scope", "Session uploads require session_id. Other scopes reject it.")
        self._check_access(scope=scope, row_owner=user_id, user_id=user_id, role=role, write=True)
        filename = sanitize_filename(upload.filename or "")

        target = self._registry_target(scope=scope, user_id=user_id, session_id=session_id)
        if await upload_registry.count_files(**target) >= settings.upload_max_files_per_scope:
            raise UploadError(400, "quota_exceeded", f"Scope holds {settings.upload_max_files_per_scope} files already")

        scope_dir = self._scope_dir(scope=scope, owner_user_id=user_id, session_id=session_id)
        scope_dir.mkdir(parents=True, exist_ok=True)
        temp_path = scope_dir / f".upload-{uuid4().hex}"

        sha = hashlib.sha256()
        size = 0
        try:
            with temp_path.open("wb") as out:
                while chunk := await upload.read(_CHUNK_BYTES):
                    size += len(chunk)
                    if size > settings.upload_max_file_bytes:
                        raise UploadError(413, "file_too_large", f"File exceeds {settings.upload_max_file_bytes} bytes")
                    sha.update(chunk)
                    out.write(chunk)

            if size == 0:
                raise UploadError(400, "empty_file", "Uploaded file is empty")
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise

        file_hash = sha.hexdigest()
        final_path = scope_dir / filename
        rel_path = final_path.relative_to(Path(config.upload_dir)).as_posix()
        content_type = upload.content_type or "application/octet-stream"
        row_values = dict(
            scope=scope,
            filename=filename,
            original_filename=(upload.filename or filename)[:255],
            file_path=rel_path,
            content_type=content_type[:100],
            file_size=size,
            file_hash=file_hash,
            owner_user_id=user_id,
            session_id=session_id,
        )
        existing = await upload_registry.get_by_name(filename=filename, **target)

        if existing is not None and existing.file_hash == file_hash and final_path.exists():
            # * Same name + same content: disk untouched, row refreshed
            temp_path.unlink(missing_ok=True)
            return await upload_registry.upsert_file(**row_values)

        os.replace(temp_path, final_path)
        try:
            row = await upload_registry.upsert_file(**row_values)
        except Exception:
            # ! No orphans: kill the orphans
            final_path.unlink(missing_ok=True)
            raise
        # * Extension point: post-store steps (metadata JSON, indexing) future state
        return row

    async def list_with_reconcile(
        self, *, scope: str, user_id: str, role: str, session_id: Optional[UUID] = None
    ) -> list[File]:
        if scope not in _SCOPES:
            raise UploadError(400, "invalid_scope", f"Unknown scope: {scope}")
        self._check_access(scope=scope, row_owner=user_id, user_id=user_id, role=role, write=False)
        rows = await upload_registry.list_files(
            **self._registry_target(scope=scope, user_id=user_id, session_id=session_id)
        )
        base = Path(config.upload_dir)
        for row in rows:
            if not (base / row.file_path).exists() and not (row.meta_data or {}).get("missing"):
                await upload_registry.mark_missing(row.id)
                row.meta_data = {**(row.meta_data or {}), "missing": True}
        return rows

    async def open_content(self, *, file_id: UUID, user_id: str, role: str) -> tuple[Path, File]:
        row = await upload_registry.get_file(file_id)
        if row is None:
            raise UploadError(404, "not_found", "File not found")
        self._check_access(scope=row.scope, row_owner=row.owner_user_id, user_id=user_id, role=role, write=False)
        base = Path(config.upload_dir).resolve()
        resolved = (Path(config.upload_dir) / row.file_path).resolve()
        try:
            resolved.relative_to(base)
        except ValueError:
            # ! Registry rows are server-written, but containment is rechecked at serve time anyway
            raise UploadError(404, "not_found", "File not found")
        if not resolved.is_file():
            await upload_registry.mark_missing(row.id)
            raise UploadError(404, "file_missing", "File content is missing on disk")
        return resolved, row

    async def delete(self, *, file_id: UUID, user_id: str, role: str) -> None:
        row = await upload_registry.get_file(file_id)
        if row is None:
            raise UploadError(404, "not_found", "File not found")
        self._check_access(scope=row.scope, row_owner=row.owner_user_id, user_id=user_id, role=role, write=True)
        (Path(config.upload_dir) / row.file_path).unlink(missing_ok=True)
        await upload_registry.delete_file(file_id)

    def sweep_stale_temps(self) -> int:
        """Delete .upload-* temps older than 24h; called once at startup."""
        base = Path(config.upload_dir)
        if not base.exists():
            return 0
        cutoff = time.time() - _TEMP_MAX_AGE_SECONDS
        removed = 0
        for temp in base.rglob(".upload-*"):
            try:
                if temp.is_file() and temp.stat().st_mtime < cutoff:
                    temp.unlink()
                    removed += 1
            except OSError:
                continue
        if removed:
            logger.info(f"Upload temp sweep removed {removed} stale files")
        return removed


upload_service = UploadService()
