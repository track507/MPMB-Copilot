"""
In-process job runner with a per-tenant cap on running jobs

A capped tenant waits on its own semaphore, outside the lane's queue, so it cannot delay another tenant
"""

import asyncio
import json
from collections.abc import Mapping
from dataclasses import replace
from uuid import uuid4

from app.logger import get_logger
from app.services.compute.threads import ThreadLane
from app.services.jobs.protocol import Handler, Job

logger = get_logger(__name__)


class LocalJobRunner:
    def __init__(self, handlers: Mapping[str, Handler], *, lane: ThreadLane, per_tenant: int) -> None:
        self._handlers = dict(handlers)
        self._lane = lane
        self._per_tenant = per_tenant
        self._tenant_slots: dict[str, asyncio.Semaphore] = {}
        self._live: dict[tuple[str, str], str] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    async def submit(self, job: Job) -> str:
        if job.kind not in self._handlers:
            raise ValueError(f"no handler for job kind: {job.kind}")
        job = replace(job, payload=json.loads(json.dumps(job.payload, allow_nan=False)))

        # ! Dedupe is per tenant
        live_key = (job.tenant_id, job.key) if job.key is not None else None
        if live_key is not None and live_key in self._live:
            return self._live[live_key]

        job_id = str(uuid4())
        if live_key is not None:
            self._live[live_key] = job_id
        task = asyncio.create_task(self._run(job_id, job, live_key))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job_id

    async def _run(self, job_id: str, job: Job, live_key: tuple[str, str] | None) -> None:
        slots = self._tenant_slots.setdefault(job.tenant_id, asyncio.Semaphore(self._per_tenant))
        handler = self._handlers[job.kind]
        try:
            async with slots:
                await self._lane.run(lambda: handler(job))
            logger.info("job_done", job_id=job_id, kind=job.kind, tenant_id=job.tenant_id)
        except asyncio.CancelledError:
            logger.warning("job_cancelled", job_id=job_id, kind=job.kind, tenant_id=job.tenant_id)
            raise
        except Exception as e:
            logger.error("job_failed", job_id=job_id, kind=job.kind, tenant_id=job.tenant_id, error=str(e))
        finally:
            if live_key is not None:
                self._live.pop(live_key, None)

    async def shutdown(self) -> None:
        """Drop queued jobs; a running handler cannot be interrupted"""
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._lane.shutdown()
