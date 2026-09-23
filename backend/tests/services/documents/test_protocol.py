import pytest

from app.services.documents import CacheScope, normalize


def test_normalize_preserves_line_count():
    # ! OutlineEntry.line points into this output, so folding must never add or drop a line
    raw = "a\u2019b\n\nc\u2014d\n"
    assert normalize(raw).count("\n") == raw.count("\n")


def test_normalize_folds_the_grep_hazards():
    assert normalize("page\u2019s") == "page's"
    assert normalize("\u201cquoted\u201d") == '"quoted"'
    assert normalize("\u22121 to hit") == "-1 to hit"


def test_newline_is_the_only_line_separator_left():
    # ! Read and grep count lines with splitlines(), the outline with split("\n"), so the two must agree
    raw = "a\r\nb\rc\x0cd\u2028e\u2029f\x85g\x0bh"
    out = normalize(raw)
    assert out.split("\n") == out.splitlines()
    assert out == "a\nb\nc\nd\ne\nf\ng\nh"


def test_normalize_is_idempotent():
    # ? The service re-normalizes adapter output to catch an adapter that skipped the contract
    raw = "x\u2019y \u2014 z\r\n  trailing   \n\xa0\u2026"
    once = normalize(raw)
    assert normalize(once) == once


def test_cache_scope_builds_each_kind():
    assert CacheScope.for_user("0192f3a4-1111-7abc-8def-0123456789ab").kind == "user"
    assert CacheScope.shared().key == ""
    assert CacheScope.for_source_root("mpmb_source").kind == "source_root"


@pytest.mark.parametrize("key", ["../etc", "a/b", "a\\b", "", "x y", "..", "C:"])
def test_cache_scope_rejects_keys_that_are_not_one_path_component(key):
    # ! The key becomes a directory name, so anything that could traverse or nest is refused at construction
    with pytest.raises(ValueError):
        CacheScope.for_user(key)


def test_shared_scope_carries_no_key():
    with pytest.raises(ValueError):
        CacheScope(kind="shared", key="u1")
