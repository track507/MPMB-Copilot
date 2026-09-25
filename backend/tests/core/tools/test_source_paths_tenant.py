"""
Upload roots resolve through the key scheme, so tools read exactly where uploads write

The important assertions here are agreements between two modules, not properties of one
Both sides used to build the layout independently, and two copies of a layout drift apart silently
"""

from pathlib import Path

from app.core.storage_keys import library_prefix, session_prefix, user_global_prefix
from app.core.tools.source_paths import (
    ALLOWED_ROOTS,
    ROOT_UPLOADS_GLOBAL,
    ROOT_UPLOADS_SESSION,
    ROOT_UPLOADS_SHARED,
    _build_default_roots,
    missing_root_error,
)
from app.services.uploads.service import UploadService

TENANT_A = "019f3400-0000-7000-8000-00000000000a"
TENANT_B = "019f3400-0000-7000-8000-00000000000b"
USER_A = "019f3400-0000-7000-8000-0000000000a1"
USER_B = "019f3400-0000-7000-8000-0000000000b1"
SESSION_A = "019f3400-0000-7000-8000-0000000000a2"


class FakeDeps:
    def __init__(self, tenant_id: str = TENANT_A, user_id: str = USER_A, session_id: str = SESSION_A):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.session_id = session_id
        self.edition = "2014"


def test_tools_read_the_directory_uploads_write():
    """
    The agreement that matters: one layout, spelled once

    An upload that lands somewhere the tools never look is invisible, and nothing reports it as an error
    """
    deps = FakeDeps()
    roots = _build_default_roots(deps)
    service = UploadService()

    written = service._scope_dir(scope="session", tenant_id=TENANT_A, owner_user_id=USER_A, session_id=SESSION_A)

    assert roots[ROOT_UPLOADS_SESSION] == written


def test_every_upload_root_agrees_with_the_service():
    deps = FakeDeps()
    roots = _build_default_roots(deps)
    service = UploadService()

    assert roots[ROOT_UPLOADS_GLOBAL] == service._scope_dir(
        scope="global", tenant_id=TENANT_A, owner_user_id=USER_A, session_id=None
    )
    assert roots[ROOT_UPLOADS_SHARED] == service._scope_dir(
        scope="shared", tenant_id=TENANT_A, owner_user_id=USER_A, session_id=None
    )


def test_a_session_root_nests_under_its_owner():
    """
    Nesting is what turns an authorization question into a path miss

    A caller holding someone else's session id resolves to a directory that does not exist, rather than to their files
    """
    roots = _build_default_roots(FakeDeps())

    assert roots[ROOT_UPLOADS_SESSION].as_posix().endswith(session_prefix(TENANT_A, USER_A, SESSION_A))


def test_the_same_session_id_under_a_different_user_is_a_different_directory():
    mine = _build_default_roots(FakeDeps(user_id=USER_A))[ROOT_UPLOADS_SESSION]
    theirs = _build_default_roots(FakeDeps(user_id=USER_B))[ROOT_UPLOADS_SESSION]

    assert mine != theirs


def test_two_tenants_never_share_an_upload_root():
    for root in (ROOT_UPLOADS_SESSION, ROOT_UPLOADS_GLOBAL, ROOT_UPLOADS_SHARED):
        a = _build_default_roots(FakeDeps(tenant_id=TENANT_A))[root]
        b = _build_default_roots(FakeDeps(tenant_id=TENANT_B))[root]
        assert a != b, root


def test_the_shared_root_is_the_tenants_library_not_an_instance_wide_one():
    """
    "Shared" means shared within one tenant

    An instance-wide shared directory would be the one place every tenant could read every other tenant's uploads
    """
    roots = _build_default_roots(FakeDeps(tenant_id=TENANT_A))

    assert roots[ROOT_UPLOADS_SHARED].as_posix().endswith(library_prefix(TENANT_A))


def test_the_global_root_is_one_users_library_inside_the_tenant():
    roots = _build_default_roots(FakeDeps())

    assert roots[ROOT_UPLOADS_GLOBAL].as_posix().endswith(user_global_prefix(TENANT_A, USER_A))


def test_no_upload_root_contains_a_name():
    """Keys carry identity, so a root is built from ids and the literal segments that separate them"""
    roots = _build_default_roots(FakeDeps())
    literals = {"data", "tenants", "users", "sessions", "global", "library"}
    known_ids = {TENANT_A, USER_A, SESSION_A}

    for root in (ROOT_UPLOADS_SESSION, ROOT_UPLOADS_GLOBAL, ROOT_UPLOADS_SHARED):
        for segment in roots[root].as_posix().split("/"):
            if segment in ("", "."):
                continue
            assert segment in literals or segment in known_ids, f"{segment} is neither a literal nor an id"


def test_the_six_root_literals_are_unchanged():
    """
    They are the tools' public vocabulary: the schema, the prompt, and after MCP an external contract

    Only their resolution moved, which is the whole point of resolving them through Deps
    """
    assert ALLOWED_ROOTS == frozenset(
        {
            "./data/mpmb_source/",
            "./data/mpmb_source_2024/",
            "./data/imports_source/",
            "./data/uploads/session/",
            "./data/uploads/global/",
            "./data/uploads/shared/",
        }
    )


def test_a_missing_upload_root_reads_as_nothing_uploaded():
    """
    An upload root that does not exist yet is the normal case, not a broken install

    Reporting it as a missing directory would teach the model that retrieval is failing when nothing was uploaded
    """
    for root in (ROOT_UPLOADS_SESSION, ROOT_UPLOADS_GLOBAL, ROOT_UPLOADS_SHARED):
        message = missing_root_error(root)
        assert "no files uploaded" in message
        assert "root directory missing" not in message


def test_the_corpus_roots_still_resolve_to_the_pack_layout():
    """The move put corpus under packs/, and the resolver must follow config rather than the old names"""
    roots = _build_default_roots(FakeDeps())

    for literal in ("./data/mpmb_source/", "./data/mpmb_source_2024/", "./data/imports_source/"):
        resolved = roots[literal].as_posix()
        assert "/packs/" in resolved, resolved
        assert not resolved.endswith("/data/mpmb_source"), resolved


def test_an_upload_root_is_never_a_parent_of_another_tenants(tmp_path: Path):
    """
    Containment, not just inequality

    Two roots that merely differ could still nest, and a nested root is reachable with a relative path
    """
    a = _build_default_roots(FakeDeps(tenant_id=TENANT_A))[ROOT_UPLOADS_SESSION]
    b = _build_default_roots(FakeDeps(tenant_id=TENANT_B))[ROOT_UPLOADS_SESSION]

    assert not a.as_posix().startswith(b.as_posix())
    assert not b.as_posix().startswith(a.as_posix())
