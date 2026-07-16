import pytest

from app.core.tools.mpmb_tools import Deps, _mpmb_validate_impl
from app.core.tools.validator_client import ValidatorResult


def _deps() -> Deps:
    return Deps(session_id="s", edition="2014")


def _runner(result: ValidatorResult):
    calls: list[tuple[str, str]] = []

    async def run(source: str, edition: str) -> ValidatorResult:
        calls.append((source, edition))
        return result

    return run, calls


@pytest.mark.asyncio
async def test_clean_bill():
    run, _ = _runner(ValidatorResult(ok=True))
    deps = _deps()
    out = await _mpmb_validate_impl(deps, "var x = 1;", None, run=run)
    assert "0 errors, 0 warnings" in out and "2014" in out
    assert deps.trace == [{"tool": "mpmb_validate", "edition": "2014", "chunks": [], "errors": 0, "warnings": 0}]


@pytest.mark.asyncio
async def test_groups_errors_and_warnings():
    findings = [
        {"line": 1, "column": 5, "ruleId": "no-undef", "severity": "error", "message": "'Foo' is not defined."},
        {"line": 2, "column": 1, "ruleId": "eqeqeq", "severity": "warning", "message": "Expected '===' ..."},
    ]
    run, _ = _runner(ValidatorResult(ok=True, findings=findings))
    out = await _mpmb_validate_impl(_deps(), "Foo.x = 1;", None, run=run)
    assert "1 error(s), 1 warning(s)" in out
    assert "ERRORS" in out and "WARNINGS" in out
    assert "L1:5 [no-undef]" in out


@pytest.mark.asyncio
async def test_edition_defaults_from_deps():
    run, calls = _runner(ValidatorResult(ok=True))
    deps = Deps(session_id="s", edition="2024")
    await _mpmb_validate_impl(deps, "var x = 1;", None, run=run)
    assert calls[0][1] == "2024"


@pytest.mark.asyncio
async def test_degrades_when_validator_unavailable():
    run, _ = _runner(ValidatorResult(ok=False, error="node binary not found (node)"))
    deps = _deps()
    out = await _mpmb_validate_impl(deps, "var x = 1;", None, run=run)
    assert out.startswith("[error] validator unavailable:")
    assert deps.trace[0]["error"] == "node binary not found (node)"


@pytest.mark.asyncio
async def test_size_guard(monkeypatch):
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "tool_max_file_bytes", 10)
    run, calls = _runner(ValidatorResult(ok=True))
    out = await _mpmb_validate_impl(_deps(), "x" * 100, None, run=run)
    assert out.startswith("[error] script too large") and calls == []
