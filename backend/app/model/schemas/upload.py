"""
Response models for the uploads API
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class UploadScope(str, Enum):
    session = "session"
    global_ = "global"
    shared = "shared"


class FileOut(BaseModel):
    id: UUID
    scope: str
    session_id: Optional[UUID] = None
    filename: str
    original_filename: str
    file_size: int
    content_type: str
    file_hash: str
    uploaded_at: datetime
    message_id: Optional[UUID]
    missing: bool = False


class FileListOut(BaseModel):
    files: list[FileOut]
    total: int
