"""Persistent metadata for vector index status."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import config

logger = logging.getLogger(__name__)
_AUTO_LAST_UPDATED = object()


class IndexStatusStore:
    """Reads and writes a small JSON file with index metadata."""

    def __init__(self, metadata_path: Path | None = None):
        self._metadata_path = metadata_path or Path(config.index_cache_dir) / "index_status.json"

    def load(self) -> dict[str, Any]:
        """Return the persisted metadata, or an empty dict if unavailable."""
        try:
            if not self._metadata_path.exists():
                return {}

            raw = json.loads(self._metadata_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
        except Exception as e:
            logger.warning(f"Failed to read index status metadata from {self._metadata_path}: {e}")

        return {}

    def save(
        self,
        *,
        indexed_files: int,
        total_vectors: int,
        status: str = "ready",
        last_updated: str | None | object = _AUTO_LAST_UPDATED,
    ) -> None:
        """Persist the current index status metadata to disk."""
        payload = {
            "indexed_files": indexed_files,
            "total_vectors": total_vectors,
            "status": status,
            "last_updated": (
                datetime.now(timezone.utc).isoformat() if last_updated is _AUTO_LAST_UPDATED else last_updated
            ),
        }

        self._metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self._metadata_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def clear(self) -> None:
        """Reset persisted metadata after clearing the vector index."""
        self.save(indexed_files=0, total_vectors=0, status="empty", last_updated=None)

    def rebuild_from_chunked_output(self, *, total_vectors: int, status: str = "ready") -> dict[str, Any]:
        """Reconstruct metadata from chunk JSON files when no cache exists yet."""
        output_dir = Path(config.chunked_output_dir)
        if not output_dir.exists():
            return {}

        source_keys: set[str] = set()
        last_updated: str | None = None

        for json_path in sorted(output_dir.glob("*.json")):
            try:
                chunks = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to rebuild index metadata from {json_path}: {e}")
                continue

            if not isinstance(chunks, list):
                continue

            for chunk in chunks:
                if not isinstance(chunk, dict):
                    continue

                source_file = str(chunk.get("source_file", "")).strip()
                if not source_file:
                    continue

                source_keys.add(
                    "::".join(
                        [
                            str(chunk.get("source_repo", "")).strip(),
                            str(chunk.get("edition", "")).strip(),
                            source_file,
                        ]
                    )
                )

            candidate = datetime.fromtimestamp(json_path.stat().st_mtime, tz=timezone.utc).isoformat()
            if last_updated is None or candidate > last_updated:
                last_updated = candidate

        if not source_keys and total_vectors <= 0:
            return {}

        self.save(
            indexed_files=len(source_keys),
            total_vectors=total_vectors,
            status=status,
            last_updated=last_updated,
        )

        return self.load()


index_status_store = IndexStatusStore()
