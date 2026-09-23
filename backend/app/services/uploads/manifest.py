"""
Per-query manifest of uploaded files

Rides the user prompt, never the system prefix (keeps cached system prompt)
"""

from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from app.model.orm import File
from app.services import documents
from app.services.db import db, upload_registry
from app.services.documents import CacheScope

_MAX_PER_SCOPE = 20


async def build_upload_manifest(*, session_id: Optional[UUID], user_id: str) -> str:
    """
    Short inventory of available uploads or empty string if none
    """
    if not db.is_connected:
        return ""

    sections: list[str] = []
    targets: list[tuple[str, dict[str, Any], CacheScope]] = [
        ("library", {"scope": "global", "owner_user_id": user_id}, CacheScope.for_user(user_id)),
        ("shared", {"scope": "shared"}, CacheScope.shared()),
    ]

    if session_id is not None:
        targets.insert(0, ("session", {"scope": "session", "session_id": session_id}, CacheScope.for_user(user_id)))

    for label, filters, cache_scope in targets:
        rows = await upload_registry.list_files(**filters)
        if not rows:
            continue
        names = [row.filename + _headline(row, cache_scope) for row in rows[:_MAX_PER_SCOPE]]
        extra = f" and {len(rows) - _MAX_PER_SCOPE} more" if len(rows) > _MAX_PER_SCOPE else ""
        sections.append(f"{label}: {', '.join(names)}{extra} ({len(rows)})")

    if not sections:
        return ""
    return "\n\n[uploaded files]\n" + "\n".join(sections)


def _headline(row: File, cache_scope: CacheScope) -> str:
    """
    A document's page or row count, from an existing extraction only

    The manifest runs on every turn, so an unextracted document gets no annotation rather than a synchronous extraction
    """
    extension = Path(row.filename).suffix
    if not documents.is_extractable(extension):
        return ""
    summary = documents.cached_summary(row.file_hash, extension, cache_scope)
    if summary is None:
        return ""
    if "pages" in summary:
        return f" ({summary['pages']} pages)"
    if "rows" in summary:
        return f" ({summary['rows']} rows)"
    return ""
