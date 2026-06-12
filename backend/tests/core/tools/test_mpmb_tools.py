from dataclasses import dataclass
from pathlib import Path

import pytest

from app.core.tools.mpmb_tools import Deps, _mpmb_function_impl, _mpmb_grep_impl, _mpmb_read_impl


@dataclass
class FakeCtx:
    deps: Deps


def _setup_roots(tmp_path: Path) -> tuple[dict, Deps]:
    mpmb = tmp_path / "mpmb_source"
    mpmb.mkdir()
    imports = tmp_path / "imports_source"
    imports.mkdir()
    uploads = tmp_path / "uploads"
    (uploads / "sess-1").mkdir(parents=True)
    (uploads / "global").mkdir()
    deps = Deps(session_id="sess-1", edition="2014")
    roots = {
        "./data/mpmb_source/": mpmb,
        "./data/mpmb_source_2024/": mpmb,  # reuse for test
        "./data/imports_source/": imports,
        "./data/uploads/session/": uploads / "sess-1",
        "./data/uploads/global/": uploads / "global",
    }
    return roots, deps


def test_mpmb_read_happy_path(tmp_path: Path):
    roots, deps = _setup_roots(tmp_path)
    (roots["./data/mpmb_source/"] / "a.js").write_text("line1\nline2\nline3\n")
    out = _mpmb_read_impl(roots, deps, "./data/mpmb_source/", "a.js")
    assert "line1" in out and "line3" in out


def test_mpmb_read_line_range(tmp_path: Path):
    roots, deps = _setup_roots(tmp_path)
    (roots["./data/mpmb_source/"] / "a.js").write_text("\n".join(f"line{i}" for i in range(1, 11)))
    out = _mpmb_read_impl(roots, deps, "./data/mpmb_source/", "a.js", start_line=3, end_line=5)
    assert "line3" in out and "line5" in out
    assert "line1" not in out and "line6" not in out


def test_mpmb_read_truncates_long_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "tool_read_max_lines", 10)
    roots, deps = _setup_roots(tmp_path)
    (roots["./data/mpmb_source/"] / "a.js").write_text("\n".join(f"l{i}" for i in range(1, 101)))
    out = _mpmb_read_impl(roots, deps, "./data/mpmb_source/", "a.js")
    assert "[truncated: showing 10 of 100 lines]" in out


def test_mpmb_read_error_returns_error_string(tmp_path: Path):
    roots, deps = _setup_roots(tmp_path)
    out = _mpmb_read_impl(roots, deps, "./data/mpmb_source/", "missing.js")
    assert out.startswith("[error]")


def test_mpmb_grep_happy_path(tmp_path: Path):
    roots, deps = _setup_roots(tmp_path)
    (roots["./data/mpmb_source/"] / "a.js").write_text("var SpellsList = {};")
    (roots["./data/mpmb_source/"] / "b.js").write_text("AddSubClass('a', 'b', {});")
    out = _mpmb_grep_impl(roots, deps, "./data/mpmb_source/", "SpellsList")
    assert "a.js" in out and "SpellsList" in out
    assert "b.js" not in out


def test_mpmb_grep_truncates_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "tool_grep_max_matches", 3)
    roots, deps = _setup_roots(tmp_path)
    body = "\n".join(["SpellsList"] * 20)
    (roots["./data/mpmb_source/"] / "a.js").write_text(body)
    out = _mpmb_grep_impl(roots, deps, "./data/mpmb_source/", "SpellsList")
    assert "[truncated: showing 3 of" in out


def test_mpmb_grep_invalid_regex(tmp_path: Path):
    roots, deps = _setup_roots(tmp_path)
    out = _mpmb_grep_impl(roots, deps, "./data/mpmb_source/", "[unclosed")
    assert out.startswith("[error]") and "regex" in out


def test_mpmb_grep_pattern_too_long(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "tool_grep_pattern_max_len", 10)
    roots, deps = _setup_roots(tmp_path)
    out = _mpmb_grep_impl(roots, deps, "./data/mpmb_source/", "x" * 50)
    assert out.startswith("[error]") and "pattern" in out


def test_mpmb_function_finds_var_declaration(tmp_path: Path):
    roots, deps = _setup_roots(tmp_path)
    body = "var AbilityScores = {\n  name: 'Ability Scores',\n  str: { long: 'Strength' }\n};\n\nvar Other = 1;"
    (roots["./data/mpmb_source/"] / "a.js").write_text(body)
    out = _mpmb_function_impl(roots, deps, "./data/mpmb_source/", "AbilityScores")
    assert "var AbilityScores" in out
    assert "str:" in out
    assert "var Other" not in out


def test_mpmb_function_finds_function_declaration(tmp_path: Path):
    roots, deps = _setup_roots(tmp_path)
    body = "function ParseSpell(s) {\n  return s;\n}\n\nfunction Other() { return 2; }"
    (roots["./data/mpmb_source/"] / "a.js").write_text(body)
    out = _mpmb_function_impl(roots, deps, "./data/mpmb_source/", "ParseSpell")
    assert "function ParseSpell" in out
    assert "return s;" in out
    assert "Other" not in out


def test_mpmb_function_not_found(tmp_path: Path):
    roots, deps = _setup_roots(tmp_path)
    (roots["./data/mpmb_source/"] / "a.js").write_text("var X = 1;")
    out = _mpmb_function_impl(roots, deps, "./data/mpmb_source/", "NotThere")
    assert out.startswith("[error]") and "not found" in out


def test_mpmb_grep_no_matches_is_not_an_error(tmp_path: Path):
    roots, deps = _setup_roots(tmp_path)
    (roots["./data/mpmb_source/"] / "a.js").write_text("var SpellsList = {};")
    out = _mpmb_grep_impl(roots, deps, "./data/mpmb_source/", "DoesNotOccurAnywhere")
    assert not out.startswith("[error]")
    assert "No matches" in out
    assert "DoesNotOccurAnywhere" in out


def test_mpmb_grep_reads_imports_root(tmp_path: Path):
    roots, deps = _setup_roots(tmp_path)
    (roots["./data/imports_source/"] / "ua.js").write_text("FeatsList['lucky'] = {};")
    out = _mpmb_grep_impl(roots, deps, "./data/imports_source/", "FeatsList")
    assert "ua.js" in out and "FeatsList" in out


def test_mpmb_grep_missing_upload_root_friendly(tmp_path: Path):
    roots, deps = _setup_roots(tmp_path)
    roots["./data/uploads/session/"] = tmp_path / "uploads" / "never-created"
    out = _mpmb_grep_impl(roots, deps, "./data/uploads/session/", "anything")
    assert "no files uploaded" in out


def test_mpmb_grep_skips_denied_subdirs(tmp_path: Path):
    roots, deps = _setup_roots(tmp_path)
    nm = roots["./data/mpmb_source/"] / "node_modules"
    nm.mkdir()
    (nm / "dep.js").write_text("var SpellsList = {};")
    out = _mpmb_grep_impl(roots, deps, "./data/mpmb_source/", "SpellsList")
    assert "No matches" in out


def test_mpmb_function_skips_denied_subdirs(tmp_path: Path):
    roots, deps = _setup_roots(tmp_path)
    nm = roots["./data/mpmb_source/"] / "node_modules"
    nm.mkdir()
    (nm / "dep.js").write_text("var Hidden = { a: 1 };")
    out = _mpmb_function_impl(roots, deps, "./data/mpmb_source/", "Hidden")
    assert out.startswith("[error]") and "not found" in out


def test_mpmb_grep_skips_oversized_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "tool_max_file_bytes", 100)
    roots, deps = _setup_roots(tmp_path)
    (roots["./data/mpmb_source/"] / "big.js").write_text("SpellsList " * 100)
    (roots["./data/mpmb_source/"] / "small.js").write_text("var SpellsList = {};")
    out = _mpmb_grep_impl(roots, deps, "./data/mpmb_source/", "SpellsList")
    assert "small.js" in out
    assert "big.js" not in out
