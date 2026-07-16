import json
import subprocess

import pytest

from app.core.tools import validator_client
from app.core.tools.validator_client import run_validator


def _completed(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["node"], returncode=returncode, stdout=stdout, stderr=stderr)


def _patch_spawn(monkeypatch, result_or_exc) -> None:
    def fake_spawn(_payload: bytes):
        if isinstance(result_or_exc, BaseException):
            raise result_or_exc
        return result_or_exc

    monkeypatch.setattr(validator_client, "_spawn", fake_spawn)


@pytest.mark.asyncio
async def test_parses_findings(monkeypatch):
    payload = {
        "findings": [{"line": 1, "column": 1, "ruleId": "no-undef", "severity": "error", "message": "x"}],
        "counts": {"error": 1, "warning": 0},
        "notes": [],
    }
    _patch_spawn(monkeypatch, _completed(stdout=json.dumps(payload).encode()))
    result = await run_validator("var x;", "2014")
    assert result.ok and result.counts["error"] == 1 and result.findings[0]["ruleId"] == "no-undef"


@pytest.mark.asyncio
async def test_nonzero_exit_degrades(monkeypatch):
    _patch_spawn(monkeypatch, _completed(stderr=b"boom", returncode=1))
    result = await run_validator("var x;", "2014")
    assert not result.ok and "boom" in (result.error or "")


@pytest.mark.asyncio
async def test_invalid_json_degrades(monkeypatch):
    _patch_spawn(monkeypatch, _completed(stdout=b"not json"))
    result = await run_validator("var x;", "2014")
    assert not result.ok and "JSON" in (result.error or "")


@pytest.mark.asyncio
async def test_timeout_degrades(monkeypatch):
    _patch_spawn(monkeypatch, subprocess.TimeoutExpired(cmd="node", timeout=0.01))
    result = await run_validator("var x;", "2014")
    assert not result.ok and "timed out" in (result.error or "")


@pytest.mark.asyncio
async def test_missing_script_degrades(monkeypatch):
    monkeypatch.setattr(validator_client.config, "validator_script_path", "./does/not/exist.mjs")
    result = await run_validator("var x;", "2014")
    assert not result.ok and "not found" in (result.error or "")


@pytest.mark.asyncio
async def test_missing_node_binary_degrades(monkeypatch):
    # ! guards the except clause: subprocess.run raises FileNotFoundError for a missing binary
    _patch_spawn(monkeypatch, FileNotFoundError("node"))
    result = await run_validator("var x;", "2014")
    assert not result.ok and "node binary" in (result.error or "")


@pytest.mark.asyncio
async def test_unsupported_loop_degrades(monkeypatch):
    # ! the dev-server regression: NotImplementedError stringifies to "", the repr must still surface
    _patch_spawn(monkeypatch, NotImplementedError())
    result = await run_validator("var x;", "2014")
    assert not result.ok and "NotImplementedError" in (result.error or "")
