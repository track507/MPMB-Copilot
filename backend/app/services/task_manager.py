"""Background task management with status tracking

Provides async task execution for long-running operations like indexing,
preventing the FastAPI event loop from blocking.
"""
import asyncio
import logging
from typing import Dict, Any, Callable, Optional
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    """Information about a background task"""
    id: str
    name: str
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: float = 0.0  # 0.0 - 1.0
    progress_message: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        # Convert datetimes to ISO format
        for field in ['created_at', 'started_at', 'completed_at']:
            if data[field]:
                data[field] = data[field].isoformat()
        data['status'] = self.status.value
        return data


class TaskManager:
    """Manages background tasks with status tracking

    Provides:
    - Non-blocking task execution in thread pool
    - Progress tracking and status updates
    - Task result retrieval
    - Task cancellation
    """

    def __init__(self, max_workers: int = 4):
        self.tasks: Dict[str, TaskInfo] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.active_tasks: Dict[str, asyncio.Task] = {}
        logger.info(f"TaskManager initialized with {max_workers} workers")

    async def submit_task(
        self,
        name: str,
        func: Callable,
        *args,
        **kwargs
    ) -> str:
        """Submit a background task for execution

        Args:
            name: Human-readable task name
            func: Callable to execute (can be blocking)
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            task_id: Unique identifier for tracking

        Example:
            >>> task_id = await task_manager.submit_task(
            ...     "index_chunks",
            ...     indexing_service.index_all_chunks
            ... )
        """
        task_id = str(uuid4())

        # Create task info
        task_info = TaskInfo(
            id=task_id,
            name=name,
            status=TaskStatus.PENDING,
            created_at=datetime.now(timezone.utc)
        )
        self.tasks[task_id] = task_info

        # Create and start async task
        task = asyncio.create_task(
            self._run_task(task_id, func, *args, **kwargs)
        )
        self.active_tasks[task_id] = task

        logger.info(f"Task submitted: {name} (id: {task_id})")
        return task_id

    async def _run_task(
        self,
        task_id: str,
        func: Callable,
        *args,
        **kwargs
    ):
        """Internal: Execute task in thread pool"""
        task_info = self.tasks[task_id]

        try:
            # Update status to running
            task_info.status = TaskStatus.RUNNING
            task_info.started_at = datetime.now(timezone.utc)
            logger.info(f"Task started: {task_info.name} (id: {task_id})")

            # Run blocking function in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                func,
                task_id,
                *args,
                **kwargs
            )

            # Task completed successfully
            task_info.status = TaskStatus.COMPLETED
            task_info.completed_at = datetime.now(timezone.utc)
            task_info.progress = 1.0
            task_info.result = result

            logger.info(f"Task completed: {task_info.name} (id: {task_id})")

        except asyncio.CancelledError:
            # Task was cancelled
            task_info.status = TaskStatus.CANCELLED
            task_info.completed_at = datetime.now(timezone.utc)
            logger.warning(f"Task cancelled: {task_info.name} (id: {task_id})")
            raise

        except Exception as e:
            # Task failed
            task_info.status = TaskStatus.FAILED
            task_info.completed_at = datetime.now(timezone.utc)
            task_info.error = str(e)
            logger.error(f"Task failed: {task_info.name} (id: {task_id}): {e}", exc_info=True)

        finally:
            # Cleanup active task reference
            self.active_tasks.pop(task_id, None)

    def get_task_status(self, task_id: str) -> Optional[TaskInfo]:
        """Get current status of a task

        Args:
            task_id: Task identifier

        Returns:
            TaskInfo if task exists, None otherwise
        """
        return self.tasks.get(task_id)

    def list_tasks(self, limit: int = 50) -> list[TaskInfo]:
        """List recent tasks, newest first

        Args:
            limit: Maximum number of tasks to return

        Returns:
            List of TaskInfo objects sorted by creation time
        """
        sorted_tasks = sorted(
            self.tasks.values(),
            key=lambda t: t.created_at,
            reverse=True
        )
        return sorted_tasks[:limit]

    def update_progress(
        self,
        task_id: str,
        progress: float,
        message: str = ""
    ):
        """Update task progress (call from within task function)

        Args:
            task_id: Task identifier
            progress: Progress value 0.0 - 1.0
            message: Optional progress message

        Example:
            >>> # Inside your task function:
            >>> task_manager.update_progress(task_id, 0.5, "Processing file 5/10")
        """
        task_info = self.tasks.get(task_id)
        if task_info:
            task_info.progress = max(0.0, min(1.0, progress))
            task_info.progress_message = message

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task

        Args:
            task_id: Task identifier

        Returns:
            True if task was cancelled, False if not found or already completed
        """
        task = self.active_tasks.get(task_id)
        if task and not task.done():
            task.cancel()
            logger.info(f"Task cancellation requested: {task_id}")
            return True
        return False

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Remove old task records to prevent memory buildup

        Args:
            max_age_hours: Remove tasks older than this many hours
        """
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)

        to_remove = [
            task_id for task_id, info in self.tasks.items()
            if info.created_at.timestamp() < cutoff
            and info.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
        ]

        for task_id in to_remove:
            self.tasks.pop(task_id, None)

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old task records")

    async def shutdown(self):
        """Graceful shutdown - cancel all running tasks"""
        logger.info("TaskManager shutdown initiated")

        # Cancel all active tasks
        for task_id, task in self.active_tasks.items():
            if not task.done():
                task.cancel()

        # Wait for cancellations
        if self.active_tasks:
            await asyncio.gather(*self.active_tasks.values(), return_exceptions=True)

        # Shutdown executor
        self.executor.shutdown(wait=True)
        logger.info("TaskManager shutdown complete")


# Global singleton instance
task_manager = TaskManager(max_workers=4)
