"""
Report drift between the database and the storage root

Exits non-zero when anything is found, so it can gate a deploy, and repairs nothing
Run it with: pnpm run storage:verify
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import config
from app.services.db.connection import db
from app.services.storage.verify import format_report, verify


async def main() -> int:
    await db.connect(config.resolved_database_url)
    try:
        async with db.session() as session:
            report = await verify(session)
    finally:
        await db.disconnect()

    print(format_report(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
