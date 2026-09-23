"""
The key scheme, which is a contract rather than an implementation detail

Every assertion here is something a later feature must not be allowed to break
"""

import re

import pytest

from app.core import storage_keys as keys

TENANT = "019f341f-ffdd-74e3-b2f4-53d85ee397aa"
USER = "019f36a2-0000-7000-8000-000000000001"
SESSION = "019f36a2-0000-7000-8000-000000000002"


def test_session_uploads_nest_under_their_owner():
    key = keys.session_prefix(TENANT, USER, SESSION)
    assert key == f"tenants/{TENANT}/users/{USER}/sessions/{SESSION}"
    assert key.startswith(keys.user_prefix(TENANT, USER))


def test_every_segment_is_an_identifier_never_a_name():
    key = keys.file_key(keys.session_prefix(TENANT, USER, SESSION), "019f36a2-0000-7000-8000-000000000003")
    segments = key.split("/")
    literals = {"tenants", "users", "sessions"}
    for segment in segments:
        if segment in literals:
            continue
        assert re.fullmatch(r"[0-9a-f-]{36}", segment), f"{segment} is not an identifier"


def test_the_library_is_flat_so_folders_can_move_without_moving_bytes():
    prefix = keys.library_prefix(TENANT)
    key = keys.file_key(prefix, "019f36a2-0000-7000-8000-000000000004")
    assert key.count("/") == 3
    assert "folder" not in key


def test_the_name_index_lives_inside_the_tenant():
    assert keys.tenant_name_index_key(TENANT).startswith(keys.tenant_prefix(TENANT))


def test_shared_tenant_cannot_collide_with_a_real_tenant_id():
    assert not re.fullmatch(r"[0-9a-f-]{36}", keys.SHARED_TENANT)


@pytest.mark.parametrize(
    "prefix",
    [
        keys.tenant_prefix(TENANT),
        keys.user_prefix(TENANT, USER),
        keys.session_prefix(TENANT, USER, SESSION),
        keys.library_prefix(TENANT),
        keys.pack_prefix("mpmb"),
    ],
)
def test_no_prefix_starts_or_ends_with_a_separator(prefix):
    assert not prefix.startswith("/")
    assert not prefix.endswith("/")
