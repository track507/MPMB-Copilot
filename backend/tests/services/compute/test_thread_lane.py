import asyncio
import contextvars
import threading
import time

import pytest

from app.services.compute.threads import ThreadLane


async def test_work_runs_off_the_event_loop_thread():
    lane = ThreadLane("t", 1)
    loop_thread = threading.get_ident()

    assert await lane.run(threading.get_ident) != loop_thread
    lane.shutdown()


async def test_the_pool_bounds_concurrency():
    lane = ThreadLane("t", 2)
    lock = threading.Lock()
    active = peak = 0

    def work() -> None:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1

    await asyncio.gather(*(lane.run(work) for _ in range(6)))

    assert peak == 2
    lane.shutdown()


async def test_the_loop_stays_responsive_while_work_blocks():
    lane = ThreadLane("t", 1)
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    task = asyncio.create_task(ticker())
    await lane.run(lambda: time.sleep(0.2))
    task.cancel()

    assert ticks >= 5
    lane.shutdown()


async def test_an_exception_reaches_the_caller():
    lane = ThreadLane("t", 1)

    def boom() -> None:
        raise ValueError("model exploded")

    with pytest.raises(ValueError, match="model exploded"):
        await lane.run(boom)
    lane.shutdown()


async def test_the_callers_context_reaches_the_worker_thread():
    request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id")
    request_id.set("req-123")
    lane = ThreadLane("t", 1)

    assert await lane.run(request_id.get) == "req-123"
    lane.shutdown()
