from evals.export_feedback import build_candidate, dedupe_ids, slugify


def test_slugify_basic() -> None:
    assert slugify("How do I add a Spell?") == "how-do-i-add-a-spell"


def test_build_candidate_includes_edition_and_note() -> None:
    c = build_candidate("how do I add a feat", "2024", "wrong syntax", "s1", "m1")
    assert c["query"] == "how do I add a feat"
    assert c["edition"] == "2024"
    assert c["expect"] == {}
    assert c["_note"] == "wrong syntax"
    assert c["_source"] == {"session_id": "s1", "message_id": "m1"}


def test_build_candidate_omits_empty_edition_and_note() -> None:
    c = build_candidate("query text", None, None, "s1", "m1")
    assert "edition" not in c
    assert "_note" not in c


def test_dedupe_ids_suffixes_collisions() -> None:
    out = dedupe_ids([{"id": "a"}, {"id": "a"}, {"id": "a"}])
    assert [c["id"] for c in out] == ["a", "a-1", "a-2"]
