from typing import Optional

from pydantic import BaseModel


class TaskStatusResponse(BaseModel):
    """Response model for task status"""

    id: str
    name: str
    status: str
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    progress: float
    progress_message: str
    result: Optional[dict]
    error: Optional[str]


class TaskListResponse(BaseModel):
    """Response model for task listing"""

    tasks: list[dict]
    total: int
