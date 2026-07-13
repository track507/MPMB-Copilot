from evals.export_feedback import build_candidate, dedupe_ids, slugify, summarize_retrieved


def _trace(chunks_per_search: list[list[dict]]) -> list[dict]:
    return [
        {"tool": "mpmb_search", "query": f"q{i}", "edition": None, "chunks": chunks}
        for i, chunks in enumerate(chunks_per_search)
    ]


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


def test_up_vote_builds_expect_from_last_search_top_chunk() -> None:
    trace = _trace(
        [
            [{"source_file": "old/Ignored.js", "edition": "2014", "object_type": "FeatsList"}],
            [
                {"source_file": "_variables/ListsSpells.js", "edition": "2024", "object_type": "SpellsList"},
                {"source_file": "other/Second.js", "edition": "2014", "object_type": "RaceList"},
            ],
        ]
    )
    case = build_candidate("add a spell", "2024", None, "s1", "m1", rating="up", retrieval=trace)
    # ? Top chunk of the LAST non-empty search: rank order, not score order (rerank reorders)
    assert case["expect"] == {"source_substring": "ListsSpells.js", "object_type": "SpellsList", "edition": "2024"}
    assert case["_rating"] == "up"


def test_expect_skips_unknown_edition_and_missing_object_type() -> None:
    trace = _trace([[{"source_file": "_functions/Functions1.js", "edition": "unknown"}]])
    case = build_candidate("q", None, None, "s1", "m1", rating="up", retrieval=trace)
    assert case["expect"] == {"source_substring": "Functions1.js"}


def test_up_vote_without_trace_stays_skeleton() -> None:
    case = build_candidate("q", None, None, "s1", "m1", rating="up", retrieval=None)
    assert case["expect"] == {}


def test_down_vote_keeps_expect_empty_but_carries_retrieved() -> None:
    trace = _trace(
        [[{"source_file": "a.js", "edition": "2014", "object_type": "FeatsList", "chunk_type": "object_literal"}]]
    )
    case = build_candidate("q", "2014", "wrong edition", "s1", "m1", rating="down", retrieval=trace)
    # ! Never auto-fill expect from a bad answer's trace - it encodes the failure, not the expectation
    assert case["expect"] == {}
    assert case["_retrieved"][0]["top"][0]["source_file"] == "a.js"
    assert case["_note"] == "wrong edition"


def test_retrieved_summary_caps_per_search() -> None:
    trace = _trace([[{"source_file": f"f{i}.js"} for i in range(6)]])
    summary = summarize_retrieved(trace)
    assert len(summary[0]["top"]) == 3
