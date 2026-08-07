"""
build_upload_manifest - per-query inventory that rides the user prompt

db + registry are mocked; this asserts the manifest string shape only
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.uploads.manifest as manifest_mod
from app.services.uploads.manifest import build_upload_manifest


def _rows(*names):
    return [SimpleNamespace(filename=n) for n in names]


@pytest.fixture
def scopes(monkeypatch):
    """
    db connected; list_files serves per-scope rows from the returned dict
    """
    by_scope: dict[str, list] = {"session": [], "global": [], "shared": []}

    async def fake_list_files(*, scope, **_):
        return by_scope.get(scope, [])

    monkeypatch.setattr(manifest_mod, "db", SimpleNamespace(is_connected=True))
    monkeypatch.setattr(manifest_mod, "upload_registry", SimpleNamespace(list_files=fake_list_files))
    return by_scope


async def test_empty_scopes_returns_blank(scopes):
    assert await build_upload_manifest(session_id=uuid4(), user_id="u1") == ""


async def test_sections_in_order_session_library_shared(scopes):
    scopes["session"] = _rows("s.js")
    scopes["global"] = _rows("g.js")
    scopes["shared"] = _rows("sh.js")

    result = await build_upload_manifest(session_id=uuid4(), user_id="u1")

    assert result.startswith("\n\n[uploaded files]\n")
    assert result.index("session:") < result.index("library:") < result.index("shared:")
    assert "s.js" in result and "g.js" in result and "sh.js" in result


async def test_no_session_id_omits_session_section(scopes):
    scopes["global"] = _rows("g.js")

    result = await build_upload_manifest(session_id=None, user_id="u1")

    assert "session:" not in result
    assert "library:" in result


async def test_pdf_files_annotated(scopes):
    scopes["global"] = _rows("guide.pdf")

    result = await build_upload_manifest(session_id=None, user_id="u1")

    assert "guide.pdf (pdf - not readable yet)" in result


async def test_over_cap_files_elided(scopes):
    scopes["global"] = _rows(*[f"f{i}.js" for i in range(21)])

    result = await build_upload_manifest(session_id=None, user_id="u1")

    assert "and 1 more" in result  # 21 - 20 cap
    assert "(21)" in result  # total count stays uncapped


async def test_db_down_returns_blank(monkeypatch):
    monkeypatch.setattr(manifest_mod, "db", SimpleNamespace(is_connected=False))
    assert await build_upload_manifest(session_id=uuid4(), user_id="u1") == ""
