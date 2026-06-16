"""Deterministic retrieval-eval scoring.

Pure functions over already-retrieved chunks - no Qdrant or network needed, so the
scoring is fully unit-testable. The runner (`run_eval.py`) supplies real chunks from
the live retriever; tests supply synthetic ones.
"""


def chunk_matches(chunk: dict, expect: dict) -> bool:
    """True if a returned chunk satisfies every key present in `expect`.

    Supported expectation keys:
      - object_type: exact match on chunk metadata.object_type
      - source_substring: case-insensitive substring of chunk source_file
      - edition: exact match on chunk edition
    """
    if "object_type" in expect:
        if (chunk.get("metadata") or {}).get("object_type") != expect["object_type"]:
            return False
    if "source_substring" in expect:
        if expect["source_substring"].lower() not in str(chunk.get("source_file", "")).lower():
            return False
    if "edition" in expect:
        if chunk.get("edition") != expect["edition"]:
            return False
    return True


def score_case(chunks: list[dict], expect: dict) -> dict:
    """Rank (1-based) of the first matching chunk and its reciprocal rank (for MRR)."""
    for index, chunk in enumerate(chunks, start=1):
        if chunk_matches(chunk, expect):
            return {"hit": True, "rank": index, "rr": 1.0 / index}
    return {"hit": False, "rank": None, "rr": 0.0}


def aggregate(results: list[dict]) -> dict:
    """Hit-rate and mean reciprocal rank across scored cases."""
    count = len(results)
    hits = sum(1 for r in results if r["hit"])
    mrr = (sum(r["rr"] for r in results) / count) if count else 0.0
    return {"cases": count, "hits": hits, "hit_rate": (hits / count) if count else 0.0, "mrr": mrr}
