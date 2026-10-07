import asyncio
import threading

import pytest

from app.services.compute.threads import ThreadLane
from app.services.jobs.local import LocalJobRunner
from app.services.jobs.protocol import Job

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


class Recorder:
    def __init__(self) -> None:
        self.gates: dict[str, threading.Event] = {}
        self.started: list[str] = []
        self.done: list[str] = []

    def gate(self, name: str) -> threading.Event:
        return self.gates.setdefault(name, threading.Event())

    def work(self, job: Job) -> None:
        name = job.payload["name"]
        self.started.append(name)
        if not self.gate(name).wait(timeout=5):
            raise TimeoutError(f"{name} was never released")
        self.done.append(name)


def _runner(recorder: Recorder, *, workers: int = 2, per_tenant: int = 1) -> LocalJobRunner:
    return LocalJobRunner({"work": recorder.work}, lane=ThreadLane("test-job", workers), per_tenant=per_tenant)


async def _until(predicate, timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


def _job(tenant: str, name: str, key: str | None = None) -> Job:
    return Job(kind="work", tenant_id=tenant, payload={"name": name}, key=key)


async def test_a_tenant_at_its_cap_does_not_block_another_tenant():
    recorder = Recorder()
    runner = _runner(recorder, workers=2, per_tenant=1)
    for name in ("a1", "a2", "a3"):
        await runner.submit(_job(TENANT_A, name))
    await runner.submit(_job(TENANT_B, "b1"))
    recorder.gate("b1").set()

    await _until(lambda: "b1" in recorder.done)

    assert set(recorder.started) == {"a1", "b1"}
    for name in ("a1", "a2", "a3"):
        recorder.gate(name).set()
    await _until(lambda: len(recorder.done) == 4)
    await runner.shutdown()


async def test_a_live_key_dedupes_and_a_finished_one_does_not():
    recorder = Recorder()
    runner = _runner(recorder)

    first = await runner.submit(_job(TENANT_A, "x", key="ocr:abc"))
    assert await runner.submit(_job(TENANT_A, "x", key="ocr:abc")) == first

    recorder.gate("x").set()
    await _until(lambda: recorder.done == ["x"])
    await _until(lambda: "ocr:abc" not in runner._live)

    assert await runner.submit(_job(TENANT_A, "x", key="ocr:abc")) != first
    await runner.shutdown()


async def test_an_unknown_kind_is_refused_at_submit():
    runner = _runner(Recorder())

    with pytest.raises(ValueError, match="no handler"):
        await runner.submit(Job(kind="nope", tenant_id=TENANT_A, payload={}))
    await runner.shutdown()


async def test_a_payload_that_could_not_cross_a_process_is_refused_at_submit():
    runner = _runner(Recorder())

    with pytest.raises(TypeError):
        await runner.submit(Job(kind="work", tenant_id=TENANT_A, payload={"path": object()}))
    await runner.shutdown()


async def test_a_failing_handler_does_not_stop_the_next_job():
    calls: list[str] = []

    def flaky(job: Job) -> None:
        calls.append(job.payload["name"])
        if job.payload["name"] == "bad":
            raise RuntimeError("corrupt page")

    runner = LocalJobRunner({"work": flaky}, lane=ThreadLane("test-job", 1), per_tenant=1)
    await runner.submit(_job(TENANT_A, "bad"))
    await runner.submit(_job(TENANT_A, "good"))

    await _until(lambda: calls == ["bad", "good"])
    await runner.shutdown()


async def test_the_same_key_from_two_tenants_runs_twice():
    recorder = Recorder()
    runner = _runner(recorder)

    first = await runner.submit(_job(TENANT_A, "a", key="ocr:same-hash"))
    second = await runner.submit(_job(TENANT_B, "b", key="ocr:same-hash"))
    recorder.gate("a").set()
    recorder.gate("b").set()
    await _until(lambda: sorted(recorder.done) == ["a", "b"])

    assert first != second
    await runner.shutdown()


async def test_a_handler_receives_the_payload_an_out_of_process_runner_would():
    received: list[dict] = []
    runner = LocalJobRunner(
        {"work": lambda job: received.append(job.payload)}, lane=ThreadLane("test-job", 1), per_tenant=1
    )
    payload = {"pages": (1, 2), 3: "int key"}

    await runner.submit(Job(kind="work", tenant_id=TENANT_A, payload=payload))
    await _until(lambda: received)

    assert received == [{"pages": [1, 2], "3": "int key"}]
    assert received[0] is not payload
    await runner.shutdown()


async def test_a_non_finite_number_is_refused_at_submit():
    runner = _runner(Recorder())

    with pytest.raises(ValueError):
        await runner.submit(Job(kind="work", tenant_id=TENANT_A, payload={"score": float("nan")}))
    await runner.shutdown()
