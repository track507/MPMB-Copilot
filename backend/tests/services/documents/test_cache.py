from pathlib import Path

import pytest

from app.services.documents import CacheScope, Extraction, OutlineEntry, cache

HASH_A = "a" * 64
HASH_B = "b" * 64
USER = CacheScope.for_user("u1")


def _extraction(text: str = "[page 1]\nhello") -> Extraction:
    return Extraction(
        text=text,
        outline=[OutlineEntry(line=1, kind="section", label="Intro", level=0)],
        pages_without_text=[],
        summary={"pages": 1},
    )


def test_miss_then_write_then_hit(tmp_path: Path):
    assert cache.read_pair(USER, HASH_A, "pdf", "1", base=tmp_path) is None
    cache.write_pair(USER, HASH_A, "pdf", "1", _extraction(), ".pdf", base=tmp_path)

    hit = cache.read_pair(USER, HASH_A, "pdf", "1", base=tmp_path)
    assert hit is not None
    assert hit.text_path.read_text(encoding="utf-8") == "[page 1]\nhello"
    assert hit.outline == [OutlineEntry(line=1, kind="section", label="Intro", level=0)]
    assert hit.summary == {"pages": 1}


def test_an_extractor_version_bump_is_a_miss(tmp_path: Path):
    # ? The version is in the name, so an upgrade produces a fresh pair instead of silently renumbering a cached one
    cache.write_pair(USER, HASH_A, "pdf", "1", _extraction(), ".pdf", base=tmp_path)
    assert cache.read_pair(USER, HASH_A, "pdf", "2", base=tmp_path) is None


def test_a_txt_without_its_json_is_a_miss(tmp_path: Path):
    # ! The json is the completion marker, since two files cannot be replaced atomically together
    cache.write_pair(USER, HASH_A, "pdf", "1", _extraction(), ".pdf", base=tmp_path)
    _, json_path = cache.sidecar_paths(USER, HASH_A, "pdf", "1", base=tmp_path)
    json_path.unlink()
    assert cache.read_pair(USER, HASH_A, "pdf", "1", base=tmp_path) is None


def test_a_corrupt_json_is_a_miss(tmp_path: Path):
    cache.write_pair(USER, HASH_A, "pdf", "1", _extraction(), ".pdf", base=tmp_path)
    _, json_path = cache.sidecar_paths(USER, HASH_A, "pdf", "1", base=tmp_path)
    json_path.write_text("{not json", encoding="utf-8")
    assert cache.read_pair(USER, HASH_A, "pdf", "1", base=tmp_path) is None


def test_the_stream_keeps_bare_newlines_on_every_platform(tmp_path: Path):
    # ! A \r\n on disk would shift every line count on Windows
    document = cache.write_pair(USER, HASH_A, "pdf", "1", _extraction("a\nb\nc"), ".pdf", base=tmp_path)
    assert document.text_path.read_bytes() == b"a\nb\nc"


def test_each_scope_kind_gets_its_own_bucket(tmp_path: Path):
    assert cache.bucket_dir(USER, tmp_path) == tmp_path / "u1"
    assert cache.bucket_dir(CacheScope.shared(), tmp_path) == tmp_path / "shared"
    assert (
        cache.bucket_dir(CacheScope.for_source_root("mpmb_source"), tmp_path)
        == tmp_path / "_source_roots" / "mpmb_source"
    )


def test_one_users_extraction_is_invisible_to_another(tmp_path: Path):
    # ! Derived text inherits its source's isolation, so the same bytes do not share a bucket across users
    cache.write_pair(USER, HASH_A, "pdf", "1", _extraction(), ".pdf", base=tmp_path)
    assert cache.read_pair(CacheScope.for_user("u2"), HASH_A, "pdf", "1", base=tmp_path) is None


def test_a_hash_that_is_not_a_digest_is_refused(tmp_path: Path):
    with pytest.raises(ValueError):
        cache.sidecar_paths(USER, "../../etc/passwd", "pdf", "1", base=tmp_path)


def test_unlink_removes_every_version_for_one_hash_in_one_bucket(tmp_path: Path):
    for version in ("1", "2"):
        cache.write_pair(USER, HASH_A, "pdf", version, _extraction(), ".pdf", base=tmp_path)
    cache.write_pair(USER, HASH_B, "pdf", "1", _extraction(), ".pdf", base=tmp_path)
    cache.write_pair(CacheScope.shared(), HASH_A, "pdf", "1", _extraction(), ".pdf", base=tmp_path)

    assert cache.unlink_hash(USER, HASH_A, base=tmp_path) == 4

    assert cache.read_pair(USER, HASH_B, "pdf", "1", base=tmp_path) is not None
    assert cache.read_pair(CacheScope.shared(), HASH_A, "pdf", "1", base=tmp_path) is not None


def test_sweep_keeps_known_hashes_removes_orphans_and_never_touches_source_roots(tmp_path: Path):
    cache.write_pair(USER, HASH_A, "pdf", "1", _extraction(), ".pdf", base=tmp_path)
    cache.write_pair(USER, HASH_B, "pdf", "1", _extraction(), ".pdf", base=tmp_path)
    source = CacheScope.for_source_root("mpmb_source")
    cache.write_pair(source, HASH_B, "pdf", "1", _extraction(), ".pdf", base=tmp_path)

    counts = cache.sweep_orphans({"u1": {HASH_A}}, base=tmp_path)

    assert counts == {"kept": 2, "removed": 2, "errors": 0}
    assert cache.read_pair(USER, HASH_A, "pdf", "1", base=tmp_path) is not None
    assert cache.read_pair(USER, HASH_B, "pdf", "1", base=tmp_path) is None
    # ? Source-root documents have no registry rows by design, so the sweep has no way to judge them
    assert cache.read_pair(source, HASH_B, "pdf", "1", base=tmp_path) is not None
