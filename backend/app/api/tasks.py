"""Task management API endpoints

Provides endpoints for checking status of background tasks (indexing, etc.)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.task_manager import task_manager, TaskStatus
from app.model import TaskStatusResponse, TaskListResponse

router = APIRouter()

class TaskListResponse(BaseModel):
	"""Response model for task listing"""
	tasks: list[dict]
	total: int

@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
	"""Get status of a specific background task"""
	task_info = task_manager.get_task_status(task_id)

	if not task_info:
		raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

	return task_info.to_dict()

@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(limit: int = 20):
	"""List recent background tasks"""
	limit = min(limit, 100)  # Cap at 100

	tasks = task_manager.list_tasks(limit=limit)

	return {
		"tasks": [t.to_dict() for t in tasks],
		"total": len(task_manager.tasks)
	}

@router.delete("/tasks/{task_id}")
async def cancel_task(task_id: str):
	"""Cancel a running background task"""
	task_info = task_manager.get_task_status(task_id)

	if not task_info:
		raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

	if task_info.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
		raise HTTPException(
			status_code=400,
			detail=f"Cannot cancel task with status: {task_info.status}"
		)

	cancelled = await task_manager.cancel_task(task_id)

	if cancelled:
		return {"message": f"Task {task_id} cancellation requested"}
	else:
		raise HTTPException(
			status_code=400,
			detail="Task could not be cancelled (may have already completed)"
		)
