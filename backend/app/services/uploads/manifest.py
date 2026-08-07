"""
Per-query manifest of uploaded files

Rides the user prompt, never the system prefix (keeps cached system prompt)
"""

from typing import Optional
from uuid import UUID

from app.services.db import db, upload_registry

_MAX_PER_SCOPE = 20


async def build_upload_manifest(*, session_id: Optional[UUID], user_id: str) -> str:
    """
    Short inventory of available uploads or empty string if none
    """
    if not db.is_connected:
        return ""

    sections: list[str] = []
    targets: list[tuple[str, dict]] = [
        ("library", {"scope": "global", "owner_user_id": user_id}),
        ("shared", {"scope": "shared"}),
    ]

    if session_id is not None:
        targets.insert(0, ("session", {"scope": "session", "session_id": session_id}))

    for label, filters in targets:
        rows = await upload_registry.list_files(**filters)
        if not rows:
            continue
        names = [
            row.filename + (" (pdf - not readable yet)" if row.filename.lower().endswith(".pdf") else "")
            for row in rows[:_MAX_PER_SCOPE]
        ]
        extra = f" and {len(rows) - _MAX_PER_SCOPE} more" if len(rows) > _MAX_PER_SCOPE else ""
        sections.append(f"{label}: {', '.join(names)}{extra} ({len(rows)})")

    if not sections:
        return ""
    return "\n\n[uploaded files]\n" + "\n".join(sections)
