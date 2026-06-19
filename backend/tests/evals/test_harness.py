from evals.harness import aggregate, chunk_matches, format_comparison, score_case


def _chunk(source_file="x.js", object_type=None, edition="2014"):
    return {"source_file": source_file, "edition": edition, "metadata": {"object_type": object_type}}


def test_chunk_matches_on_object_type_and_substring():
    c = _chunk(source_file="imports/spells_phb.js", object_type="SpellsList")
    assert chunk_matches(c, {"object_type": "SpellsList"})
    assert chunk_matches(c, {"source_substring": "spells"})
    assert not chunk_matches(c, {"object_type": "RaceList"})
    assert not chunk_matches(c, {"source_substring": "feats"})


def test_chunk_matches_respects_edition():
    assert not chunk_matches(_chunk(edition="2014"), {"edition": "2024"})
    assert chunk_matches(_chunk(edition="2024"), {"edition": "2024"})


def test_chunk_matches_requires_all_keys():
    c = _chunk(source_file="imports/spells.js", object_type="SpellsList", edition="2014")
    assert chunk_matches(c, {"object_type": "SpellsList", "edition": "2014"})
    assert not chunk_matches(c, {"object_type": "SpellsList", "edition": "2024"})


def test_score_case_reports_first_matching_rank():
    chunks = [_chunk(object_type="FeatsList"), _chunk(object_type="SpellsList")]
    r = score_case(chunks, {"object_type": "SpellsList"})
    assert r["hit"] is True
    assert r["rank"] == 2
    assert r["rr"] == 0.5


def test_score_case_miss():
    r = score_case([_chunk(object_type="FeatsList")], {"object_type": "SpellsList"})
    assert r["hit"] is False
    assert r["rank"] is None
    assert r["rr"] == 0.0


def test_aggregate_hit_rate_and_mrr():
    agg = aggregate([{"hit": True, "rank": 1, "rr": 1.0}, {"hit": False, "rank": None, "rr": 0.0}])
    assert agg["cases"] == 2
    assert agg["hits"] == 1
    assert agg["hit_rate"] == 0.5
    assert agg["mrr"] == 0.5


def test_aggregate_empty_is_safe():
    agg = aggregate([])
    assert agg == {"cases": 0, "hits": 0, "hit_rate": 0.0, "mrr": 0.0}


def test_format_comparison_shows_deltas():
    base = {"cases": 8, "hits": 4, "hit_rate": 0.5, "mrr": 0.4}
    rer = {"cases": 8, "hits": 6, "hit_rate": 0.75, "mrr": 0.55}
    out = format_comparison(base, rer)
    assert "baseline: 4/8" in out
    assert "reranked: 6/8" in out
    assert "+25%" in out  # hit_rate delta
    assert "+0.150" in out  # mrr delta
