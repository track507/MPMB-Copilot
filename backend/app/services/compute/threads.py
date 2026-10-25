"""
A compute lane backed by a bounded thread pool

onnxruntime releases the GIL inside run(), so threads give real parallelism for inference
"""

import asyncio
import contextvars
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")


class ThreadLane:
    def __init__(self, name: str, workers: int) -> None:
        self.name = name
        self.workers = workers
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name)

    async def run(self, fn: Callable[[], T]) -> T:
        # ! Carries the caller's contextvars, request_id included
        context = contextvars.copy_context()

        def call() -> T:
            return context.run(fn)

        return await asyncio.get_running_loop().run_in_executor(self._pool, call)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
