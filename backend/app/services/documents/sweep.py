"""
On-demand orphan sweep for the extraction cache

Run from backend/: uv run --no-sync python -m app.services.documents.sweep
Not a startup pass: session deletes are soft, so orphans come only from a failed unlink or a crash
Imports the database layer, which is why the package __init__ never imports this module
"""

import asyncio
import json

from app.config import config
from app.services.db import db, upload_registry
from app.services.documents import cache


async def sweep() -> dict[str, int]:
    await db.connect(config.resolved_database_url)
    try:
        by_owner = await upload_registry.hashes_by_bucket()
    finally:
        await db.disconnect()
    # ? The registry keys buckets by owner, and the cache names the ownerless shared bucket on disk
    known = {cache.SHARED_DIR if owner is None else owner: hashes for owner, hashes in by_owner.items()}
    return cache.sweep_orphans(known)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(sweep())))
