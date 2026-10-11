"""
The one place that knows the storage layout

Keys built from immutable identity, never from a name, fold, or audience
A key that can change is a key that breaks every ref to it, so nothing mutable happens here
"""

import re

SHARED_TENANT = "_shared"
DEFAULT_TENANT_ID = "019f3400-0000-7000-8000-000000000000"
META_NAME = "_meta.json"
NAME_INDEX_NAME = "by-name.json"
# ! Breadcrumb leaves, never valid upload names
RESERVED_NAMES = frozenset({META_NAME, NAME_INDEX_NAME})

_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9_-]+")


def _segment(value: str) -> str:
    """
    One identity segment of a key, refused unless it is letters, digits, "_" or "-"

    ! An allowlist, so no value can add, remove or climb a path level on any OS
    """
    if not _SAFE_SEGMENT.fullmatch(value):
        raise ValueError(f"unsafe storage key segment: {value!r}")
    return value


def tenant_prefix(tenant_id: str) -> str:
    return f"tenants/{_segment(tenant_id)}"


def tenant_meta_key(tenant_id: str) -> str:
    return f"{tenant_prefix(tenant_id=tenant_id)}/{META_NAME}"


def tenant_name_index_key(tenant_id: str) -> str:
    return f"{tenant_prefix(tenant_id=tenant_id)}/{NAME_INDEX_NAME}"


def library_prefix(tenant_id: str) -> str:
    return f"{tenant_prefix(tenant_id=tenant_id)}/library"


def user_prefix(tenant_id: str, user_id: str) -> str:
    return f"{tenant_prefix(tenant_id=tenant_id)}/users/{_segment(user_id)}"


def user_meta_key(tenant_id: str, user_id: str) -> str:
    return f"{user_prefix(tenant_id, user_id)}/{META_NAME}"


def user_global_prefix(tenant_id: str, user_id: str) -> str:
    return f"{user_prefix(tenant_id, user_id)}/global"


def session_prefix(tenant_id: str, user_id: str, session_id: str) -> str:
    return f"{user_prefix(tenant_id, user_id)}/sessions/{_segment(session_id)}"


def session_meta_key(tenant_id: str, user_id: str, session_id: str) -> str:
    return f"{session_prefix(tenant_id, user_id, session_id)}/{META_NAME}"


def file_key(prefix: str, file_id: str) -> str:
    return f"{prefix}/{_segment(file_id)}"


def pack_prefix(pack_id: str) -> str:
    return f"packs/{_segment(pack_id)}"
