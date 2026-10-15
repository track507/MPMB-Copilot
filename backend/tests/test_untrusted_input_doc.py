import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "UNTRUSTED_INPUT.md"
_PATH = re.compile(r"`((?:backend|frontend|docs|\.github)/[^`:\s]+)(?::\d+)?`")


def test_every_path_the_inventory_names_exists():
    named = _PATH.findall(DOC.read_text(encoding="utf-8"))
    missing = [p for p in named if not (REPO / p).exists()]
    assert named, "the inventory names no paths"
    assert missing == [], "update docs/UNTRUSTED_INPUT.md: " + ", ".join(missing)
