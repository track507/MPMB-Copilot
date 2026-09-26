"""
Breadcrumbs written beside the data they describe

Every payload here is derived from a row, so the row stays the truth and a breadcrumb is only a projection
They exist for two readers: a human looking at the tree, and an admin view that wants ownership without joining four tables
They also carry enough to reconstruct ownership if Postgres is lost, which is the only reason they repeat fields the database already holds
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.config import config
from app.core.storage_keys import tenant_name_index_key
from app.logger import get_logger

logger = get_logger(__name__)

# ! Reserved names inside a tenant prefix: generated, never a user's upload
META_FILENAME = "_meta.json"
NAME_INDEX_FILENAME = "by-name.json"
RESERVED_FILENAMES: frozenset[str] = frozenset({META_FILENAME, NAME_INDEX_FILENAME})


def path_for(key: str) -> Path:
    """Resolve a storage key against the one storage root"""
    return Path(config.data_dir) / key


def _isoformat(value: Optional[datetime]) -> Optional[str]:
    # ? Stored as UTC ISO-8601 so a breadcrumb read on another machine means the same instant
    return value.isoformat() if value is not None else None


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """
    Write through a sibling temp file and a single rename

    ! The temp file is a sibling because os.replace is only atomic within one filesystem
    ? A reader therefore sees either the previous document or the next one, never half of either
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".meta-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
            json.dump(payload, out, indent=2, sort_keys=True)
            out.write("\n")
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def write_meta(key: str, payload: dict[str, Any]) -> None:
    """
    Write a breadcrumb beside the data it describes

    Called after the commit and never inside it, because an object store cannot join a database transaction
    A failure is logged and swallowed: the row is the truth, and storage_verify is what finds the drift
    """
    try:
        _atomic_write(path_for(key), payload)
    except OSError as e:
        logger.warning(f"could not write breadcrumb {key}: {e}")


def read_meta(key: str) -> Optional[dict[str, Any]]:
    """
    Read one breadcrumb, or None when it is absent or unreadable

    ? A corrupt breadcrumb reads as absent because it is derived: the verifier reports it rather than a reader failing on it
    """
    try:
        raw = path_for(key).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def tenant_meta_payload(*, tenant_id: str, slug: str, name: str, created_at: Optional[datetime]) -> dict[str, Any]:
    return {"id": tenant_id, "kind": "tenant", "slug": slug, "name": name, "created_at": _isoformat(created_at)}


def user_meta_payload(
    *, user_id: str, tenant_id: str, username: str, role: str, created_at: Optional[datetime]
) -> dict[str, Any]:
    return {
        "id": user_id,
        "kind": "user",
        "tenant_id": tenant_id,
        "username": username,
        "role": role,
        "created_at": _isoformat(created_at),
    }


def session_meta_payload(
    *, session_id: str, tenant_id: str, user_id: str, created_at: Optional[datetime]
) -> dict[str, Any]:
    """
    Ownership only

    ! The title is deliberately absent: it is renamed freely, and carrying it would make every rename a drift finding
    """
    return {
        "id": session_id,
        "kind": "session",
        "tenant_id": tenant_id,
        "user_id": user_id,
        "created_at": _isoformat(created_at),
    }


def write_name_index(tenant_id: str, users: list[dict[str, str]]) -> None:
    """
    Regenerate one tenant's username index

    Readability without walking prefixes, which an object store charges for and a filesystem is merely slow at
    ! It lives inside the tenant prefix because it holds names: one root-level index would expose every tenant's usernames to anyone who can list the bucket
    """
    ordered = sorted(users, key=lambda entry: entry.get("username", ""))
    write_meta(tenant_name_index_key(tenant_id), {"tenant_id": tenant_id, "users": ordered})
