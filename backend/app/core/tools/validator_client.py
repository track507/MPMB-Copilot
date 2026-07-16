"""
This is one of potentially two transport layers depending on latency

Transport 1: A script
Tranposrt 2: A node microservice so it stays warm

Spawns `node scripts/validate/src/validate.mjs` per call with the script on stdin and a JSON verdict on stdout
The stateless JSON contract is the transport seam: a warm sidecar (transport 2) replaces this module's internals with an httpx call without touching the tool
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Optional

from app.config import config
from app.logger import get_logger

logger = get_logger(__name__)

_semaphore = asyncio.Semaphore(config.validator_max_concurrency)


@dataclass
class ValidatorResult:
    ok: bool
    findings: list[dict] = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    error: Optional[str] = None


async def run_validator(source: str, edition: str) -> ValidatorResult:
    script = config.validator_script
    if not script.exists():
        return ValidatorResult(ok=False, error=f"validator script not found at {script}")

    payload = json.dumps({"source": source, "edition": edition}).encode("utf-8")
    async with _semaphore:
        try:
            proc = await asyncio.create_subprocess_exec(
                config.validator_node_bin,
                str(script),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return ValidatorResult(ok=False, error=f"node binary not found ({config.validator_node_bin})")
        try:
            out, err = await asyncio.wait_for(proc.communicate(payload), timeout=config.validator_timeout_sec)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ValidatorResult(ok=False, error=f"validator timed out after {config.validator_timeout_sec}s")

    if proc.returncode != 0:
        detail = err.decode("utf-8", errors="replace")[:400]
        return ValidatorResult(ok=False, error=f"validator exited {proc.returncode}: {detail}")
    try:
        data = json.loads(out.decode("utf-8"))
    except ValueError as e:
        return ValidatorResult(ok=False, error=f"validator returned invalid JSON: {e}")
    return ValidatorResult(
        ok=True,
        findings=data.get("findings", []),
        counts=data.get("counts", {}),
        notes=data.get("notes", []),
    )
