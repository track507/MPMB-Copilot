from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from mpmb_repo_analyzer.__main__ import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
