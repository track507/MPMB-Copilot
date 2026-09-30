"""
The CLAUDE.md rule, enforced: only the secrets service reads a provider credential off config

import-linter cannot gate this, because config.anthropic_api_key is attribute access and not an import
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[3] / "app"
_FORBIDDEN = re.compile(r"(?:config|self)\.(?:anthropic_api_key|openai_api_key|get_llm_api_key)\b")
_ALLOWED = {Path("services/secrets/env.py")}


def test_only_the_secrets_service_reads_a_key_off_config():
    offenders: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        relative = path.relative_to(APP)
        if relative in _ALLOWED:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _FORBIDDEN.search(line):
                offenders.append(f"{relative.as_posix()}:{number}")
    assert offenders == [], "read provider keys through app.services.secrets, not config: " + ", ".join(offenders)


def test_the_guard_can_fail():
    # ! Guards the guard: a regex that matched nothing would also report no offenders
    assert _FORBIDDEN.search("        api_key = config.openai_api_key")
    assert _FORBIDDEN.search("            return self.anthropic_api_key")
    assert not _FORBIDDEN.search("        api_key = api_key_for('openai')")
