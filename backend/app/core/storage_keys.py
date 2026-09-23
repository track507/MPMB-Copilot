"""
The one place that knows the storage layout

Keys built from immutable identity, never from a name, fold, or audience
A key that can change is a key that breaks every ref to it, so nothing mutable happens here
"""

SHARED_TENANT = "_shared"
DEFAULT_TENANT_ID = "019f3400-0000-7000-8000-000000000000"


def tenant_prefix(tenant_id: str) -> str:
    return f"tenants/{tenant_id}"


def tenant_meta_key(tenant_id: str) -> str:
    return f"{tenant_prefix(tenant_id=tenant_id)}/meta.json"


def tenant_name_index_key(tenant_id: str) -> str:
    return f"{tenant_prefix(tenant_id=tenant_id)}/by-name.json"


def library_prefix(tenant_id: str) -> str:
    return f"{tenant_prefix(tenant_id=tenant_id)}/library"


def user_prefix(tenant_id: str, user_id: str) -> str:
    return f"{tenant_prefix(tenant_id=tenant_id)}/users/{user_id}"


def user_meta_key(tenant_id: str, user_id: str) -> str:
    return f"{user_prefix(tenant_id, user_id)}/_meta.json"


def user_global_prefix(tenant_id: str, user_id: str) -> str:
    return f"{user_prefix(tenant_id, user_id)}/global"


def session_prefix(tenant_id: str, user_id: str, session_id: str) -> str:
    return f"{user_prefix(tenant_id, user_id)}/sessions/{session_id}"


def session_meta_key(tenant_id: str, user_id: str, session_id: str) -> str:
    return f"{session_prefix(tenant_id, user_id, session_id)}/_meta.json"


def file_key(prefix: str, file_id: str) -> str:
    return f"{prefix}/{file_id}"


def pack_prefix(pack_id: str) -> str:
    return f"packs/{pack_id}"
