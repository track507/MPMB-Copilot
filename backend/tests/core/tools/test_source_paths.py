from pathlib import Path

import pytest

from app.core.tools.source_paths import (
    ALLOWED_EXTENSIONS,
    ALLOWED_ROOTS,
    DENIED_SUBDIRS,
    PathResolution,
    iter_searchable_files,
    missing_root_error,
    resolve_safe_path,
)


class FakeDeps:
    def __init__(self, session_id: str = "sess-test"):
        self.session_id = session_id
        self.edition = "2014"


def _make_roots(tmp_path: Path) -> dict[str, Path]:
    mpmb = tmp_path / "mpmb_source"
    mpmb.mkdir()
    imports = tmp_path / "imports_source"
    imports.mkdir()
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "sess-test").mkdir()
    (uploads / "global").mkdir()
    return {
        "./data/mpmb_source/": mpmb,
        "./data/imports_source/": imports,
        "./data/uploads/session/": uploads / "sess-test",
        "./data/uploads/global/": uploads / "global",
    }


def test_unknown_root_rejected(tmp_path: Path):
    roots = _make_roots(tmp_path)
    result = resolve_safe_path("./bogus/", "foo.js", FakeDeps(), roots)
    assert isinstance(result, PathResolution)
    assert result.error is not None
    assert result.error.startswith("[error] unknown root:")


def test_absolute_path_rejected(tmp_path: Path):
    roots = _make_roots(tmp_path)
    result = resolve_safe_path("./data/mpmb_source/", "/etc/passwd", FakeDeps(), roots)
    assert result.error and result.error.startswith("[error]")


def test_dotdot_rejected(tmp_path: Path):
    roots = _make_roots(tmp_path)
    result = resolve_safe_path("./data/mpmb_source/", "../outside.js", FakeDeps(), roots)
    assert result.error and result.error.startswith("[error]")


def test_disallowed_extension(tmp_path: Path):
    roots = _make_roots(tmp_path)
    (roots["./data/mpmb_source/"] / "secrets.pdf").write_text("x")
    result = resolve_safe_path("./data/mpmb_source/", "secrets.pdf", FakeDeps(), roots)
    assert result.error and "extension not allowed" in result.error


def test_file_too_large(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "tool_max_file_bytes", 100)
    roots = _make_roots(tmp_path)
    big = roots["./data/mpmb_source/"] / "big.js"
    big.write_text("x" * 500)
    result = resolve_safe_path("./data/mpmb_source/", "big.js", FakeDeps(), roots)
    assert result.error and "file too large" in result.error


def test_denied_subdir(tmp_path: Path):
    roots = _make_roots(tmp_path)
    (roots["./data/mpmb_source/"] / ".git").mkdir()
    (roots["./data/mpmb_source/"] / ".git" / "config").write_text("x")
    result = resolve_safe_path("./data/mpmb_source/", ".git/config", FakeDeps(), roots)
    assert result.error and "[error]" in result.error


def test_path_not_found(tmp_path: Path):
    roots = _make_roots(tmp_path)
    result = resolve_safe_path("./data/mpmb_source/", "nope.js", FakeDeps(), roots)
    assert result.error and "not found" in result.error


def test_symlink_escape_rejected(tmp_path: Path):
    roots = _make_roots(tmp_path)
    outside = tmp_path / "outside.js"
    outside.write_text("secret")
    link = roots["./data/mpmb_source/"] / "link.js"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink not supported on this platform")
    result = resolve_safe_path("./data/mpmb_source/", "link.js", FakeDeps(), roots)
    assert result.error and "[error]" in result.error


def test_session_alias_resolves_to_session_dir(tmp_path: Path):
    roots = _make_roots(tmp_path)
    target = roots["./data/uploads/session/"] / "notes.md"
    target.write_text("hello")
    result = resolve_safe_path("./data/uploads/session/", "notes.md", FakeDeps(), roots)
    assert result.error is None
    assert result.resolved_path == target.resolve()


def test_happy_path_mpmb_js(tmp_path: Path):
    roots = _make_roots(tmp_path)
    target = roots["./data/mpmb_source/"] / "Functions0.js"
    target.write_text("var x = 1;")
    result = resolve_safe_path("./data/mpmb_source/", "Functions0.js", FakeDeps(), roots)
    assert result.error is None
    assert result.resolved_path == target.resolve()


def test_allowed_extensions_list():
    assert ".js" in ALLOWED_EXTENSIONS
    assert ".md" in ALLOWED_EXTENSIONS
    assert ".pdf" not in ALLOWED_EXTENSIONS


def test_denied_subdirs_list():
    assert ".git" in DENIED_SUBDIRS
    assert "node_modules" in DENIED_SUBDIRS


def test_imports_root_resolves(tmp_path: Path):
    roots = _make_roots(tmp_path)
    target = roots["./data/imports_source/"] / "ua_feats.js"
    target.write_text("var x = 1;")
    result = resolve_safe_path("./data/imports_source/", "ua_feats.js", FakeDeps(), roots)
    assert result.error is None
    assert result.resolved_path == target.resolve()


def test_missing_upload_root_gives_friendly_message(tmp_path: Path):
    roots = _make_roots(tmp_path)
    roots["./data/uploads/session/"] = tmp_path / "uploads" / "never-created"
    result = resolve_safe_path("./data/uploads/session/", "notes.md", FakeDeps(), roots)
    assert result.error is not None
    assert "no files uploaded" in result.error
    assert "missing" not in result.error


def test_missing_root_error_messages():
    assert "chat session" in missing_root_error("./data/uploads/session/")
    assert "root directory missing" in missing_root_error("./data/mpmb_source/")
    assert "library" in missing_root_error("./data/uploads/global/")
    assert "shared library" in missing_root_error("./data/uploads/shared/")


def test_source_root_literal_matches_allowed_roots():
    from typing import get_args

    from app.core.tools.mpmb_tools import SourceRoot

    assert set(get_args(SourceRoot)) == set(ALLOWED_ROOTS)


def test_iter_searchable_files_applies_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "tool_max_file_bytes", 100)
    root = tmp_path / "src"
    (root / "sub").mkdir(parents=True)
    (root / "node_modules").mkdir()
    (root / ".hidden").mkdir()
    (root / "ok.js").write_text("var a = 1;")
    (root / "sub" / "nested.js").write_text("var b = 2;")
    (root / "skip.pdf").write_text("binary-ish")
    (root / "big.js").write_text("x" * 500)
    (root / "node_modules" / "dep.js").write_text("var c = 3;")
    (root / ".hidden" / "secret.js").write_text("var d = 4;")

    rels = sorted(rel.as_posix() for _, rel in iter_searchable_files(root))
    assert rels == ["ok.js", "sub/nested.js"]


def test_iter_searchable_files_excludes_symlink_escape(tmp_path: Path):
    root = tmp_path / "src"
    root.mkdir()
    outside = tmp_path / "outside.js"
    outside.write_text("secret")
    link = root / "link.js"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink not supported on this platform")
    rels = [rel.as_posix() for _, rel in iter_searchable_files(root)]
    assert rels == []
