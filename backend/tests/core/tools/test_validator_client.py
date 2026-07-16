import asyncio
import json

import pytest

from app.core.tools import validator_client
from app.core.tools.validator_client import run_validator


class FakeProc:
    def __init__(self, stdout: bytes, stderr: bytes = b"", returncode: int = 0, delay: float = 0.0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self._delay = delay

    async def communicate(self, _input: bytes) -> tuple[bytes, bytes]:
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode


def _patch_spawn(monkeypatch, proc: FakeProc) -> None:
    async def fake_exec(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(validator_client.asyncio, "create_subprocess_exec", fake_exec)


@pytest.mark.asyncio
async def test_parses_findings(monkeypatch):
    payload = {
        "findings": [{"line": 1, "column": 1, "ruleId": "no-undef", "severity": "error", "message": "x"}],
        "counts": {"error": 1, "warning": 0},
        "notes": [],
    }
    _patch_spawn(monkeypatch, FakeProc(json.dumps(payload).encode()))
    result = await run_validator("var x;", "2014")
    assert result.ok and result.counts["error"] == 1 and result.findings[0]["ruleId"] == "no-undef"


@pytest.mark.asyncio
async def test_nonzero_exit_degrades(monkeypatch):
    _patch_spawn(monkeypatch, FakeProc(b"", stderr=b"boom", returncode=1))
    result = await run_validator("var x;", "2014")
    assert not result.ok and "boom" in (result.error or "")


@pytest.mark.asyncio
async def test_invalid_json_degrades(monkeypatch):
    _patch_spawn(monkeypatch, FakeProc(b"not json"))
    result = await run_validator("var x;", "2014")
    assert not result.ok and "JSON" in (result.error or "")


@pytest.mark.asyncio
async def test_timeout_degrades(monkeypatch):
    monkeypatch.setattr(validator_client.config, "validator_timeout_sec", 0.01)
    _patch_spawn(monkeypatch, FakeProc(b"{}", delay=1.0))
    result = await run_validator("var x;", "2014")
    assert not result.ok and "timed out" in (result.error or "")


@pytest.mark.asyncio
async def test_missing_script_degrades(monkeypatch):
    monkeypatch.setattr(validator_client.config, "validator_script_path", "./does/not/exist.mjs")
    result = await run_validator("var x;", "2014")
    assert not result.ok and "not found" in (result.error or "")


@pytest.mark.asyncio
async def test_missing_node_binary_degrades(monkeypatch):
    # ! guards the except clause: create_subprocess_exec raises FileNotFoundError for a missing binary
    async def raise_missing(*_args, **_kwargs):
        raise FileNotFoundError("node")

    monkeypatch.setattr(validator_client.asyncio, "create_subprocess_exec", raise_missing)
    result = await run_validator("var x;", "2014")
    assert not result.ok and "node binary" in (result.error or "")
