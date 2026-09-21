from typing import Any, Optional

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
    result: Optional[dict[str, Any]]
    error: Optional[str]


class TaskListResponse(BaseModel):
    """Response model for task listing"""

    tasks: list[dict[str, Any]]
    total: int
