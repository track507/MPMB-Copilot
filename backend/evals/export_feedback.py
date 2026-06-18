"""
Export down-voted answers as candidate eval cases for manual curation

Pairs each down-vote with its question (the preceding user message) and edition, and writes skeletons to candidates.json with an empty `expect` for a someone to fill in
Never writes cases.json

Usage:
    cd backend && uv run --no-sync python -m evals.export_feedback
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from app.config import config
from app.model.orm import Message, MessageFeedback, Session
from app.services.db import db

_OUT = Path(__file__).parent / "candidates.json"


def slugify(text: str, max_len: int = 60) -> str:
    """Kebab-case id from a query string"""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].strip("-") or "candidate"


def build_candidate(query: str, edition: Optional[str], note: Optional[str], session_id: str, message_id: str) -> dict:
    """Skeleton case: query + edition are auto-filled, expect is left empty for a human"""
    case: dict = {"id": slugify(query), "query": query}
    if edition:
        case["edition"] = edition
    case["expect"] = {}
    if note:
        case["_note"] = note
    case["_source"] = {"session_id": session_id, "message_id": message_id}
    return case


def dedupe_ids(candidates: list[dict]) -> list[dict]:
    """Suffix colliding ids so each candidate id is unique within the file"""
    seen: dict[str, int] = {}
    for c in candidates:
        base = c["id"]
        if base in seen:
            seen[base] += 1
            c["id"] = f"{base}-{seen[base]}"
        else:
            seen[base] = 0
    return candidates


async def main() -> None:
    await db.connect(config.resolved_database_url)
    try:
        async with db.session() as s:
            rows = (
                await s.execute(
                    select(MessageFeedback, Message)
                    .join(Message, MessageFeedback.message_id == Message.id)
                    .where(MessageFeedback.rating == "down")
                )
            ).all()

            candidates: list[dict] = []
            for fb, msg in rows:
                user_msg = (
                    await s.execute(
                        select(Message).where(
                            Message.session_id == msg.session_id,
                            Message.sequence_number == msg.sequence_number - 1,
                        )
                    )
                ).scalar_one_or_none()
                if user_msg is None:
                    continue
                query = (
                    user_msg.content.get("text", "") if isinstance(user_msg.content, dict) else str(user_msg.content)
                )
                if not query:
                    continue

                session = (await s.execute(select(Session).where(Session.id == msg.session_id))).scalar_one_or_none()
                edition = (session.settings or {}).get("edition") if session else None
                candidates.append(build_candidate(query, edition, fb.note, str(msg.session_id), str(msg.id)))

        dedupe_ids(candidates)
        _OUT.write_text(json.dumps(candidates, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(candidates)} candidate(s) to {_OUT}")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
