"""The background job port"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Job:
    kind: str
    tenant_id: str
    # ! JSON-safe only
    payload: dict[str, Any]
    # ? Dedupe: a live key from the same tenant returns the existing job's id
    key: str | None = None


Handler = Callable[[Job], None]


@runtime_checkable
class JobRunner(Protocol):
    async def submit(self, job: Job) -> str:
        """Accept a job and return its id, before it runs"""
        ...
