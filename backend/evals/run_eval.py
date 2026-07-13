"""
Run the retrieval eval matrix against the live index

Requires Qdrant + an index built with the CURRENT embedding settings - an identity
mismatch makes retrieval refuse every query, so force-reindex first when switching embedders

Usage:
    cd backend && uv run --no-sync python -m evals.run_eval

Results print AND persist to evals/results/<timestamp>.json labeled with the embedding
identity, so cross-index runs (bge-small vs e5-large) stay comparable
Treat the first run as a baseline: per-case MISS results are signal, not test failures
"""

import asyncio
import json
import time
from pathlib import Path

from app.core.retriever import retriever
from app.services.embedding.service import embedding_service
from app.services.vector import get_vector_store
from app.settings import settings
from evals.harness import aggregate, format_matrix, score_case

_CASES = Path(__file__).parent / "cases.json"
_RESULTS_DIR = Path(__file__).parent / "results"

# * The A/B matrix: label -> settings overrides applied in-process for that pass
# ? Every config states its full rerank selection, so passes are order-independent
CONFIGS: list[tuple[str, dict]] = [
    ("baseline", {"rerank_enabled": False}),
    (
        "minilm-l6",
        {"rerank_enabled": True, "rerank_provider": "fastembed", "rerank_model": "Xenova/ms-marco-MiniLM-L-6-v2"},
    ),
    (
        "jina-v2",
        {
            "rerank_enabled": True,
            "rerank_provider": "fastembed",
            "rerank_model": "jinaai/jina-reranker-v2-base-multilingual",
        },
    ),
    # Optional tiebreakers:
    # ("minilm-l12", {"rerank_enabled": True, "rerank_provider": "fastembed", "rerank_model": "Xenova/ms-marco-MiniLM-L-12-v2"}),
    # ("bge-reranker", {"rerank_enabled": True, "rerank_provider": "fastembed", "rerank_model": "BAAI/bge-reranker-base"}),
]


async def run_config(label: str, overrides: dict, cases: list[dict]) -> dict:
    # ? Direct attribute set: in-process only; settings.update() would persist to disk
    for key, value in overrides.items():
        setattr(settings, key, value)

    print(f"\n=== {label} ===")
    results: list[dict] = []
    per_case: list[dict] = []
    reranked_seen = False
    for case in cases:
        result = await retriever.retrieve(case["query"], case.get("edition"))
        chunks = [*result.authoritative, *result.examples]
        reranked_seen = reranked_seen or any("rerank_score" in c for c in chunks)
        scored = score_case(chunks, case["expect"])
        results.append(scored)
        per_case.append({"id": case["id"], "hit": scored["hit"], "rank": scored["rank"]})
        mark = "HIT " if scored["hit"] else "MISS"
        rank = str(scored["rank"]) if scored["rank"] is not None else "-"
        print(f"[{mark}] rank={rank:>3}  {case['id']}: {case['query']}")

    # ! Rerank failures degrade silently to fused order; a config that never scored a chunk is invalid, not "no gain"
    failed = bool(overrides.get("rerank_enabled")) and not reranked_seen
    if failed:
        print(f"[FAILED] {label}: reranker never scored a chunk (model load failure?) - excluded from the matrix")
    return {"overrides": overrides, "aggregate": aggregate(results), "per_case": per_case, "failed": failed}


async def main() -> None:
    store = get_vector_store()
    if not await store.health_check():
        await store.connect()

    cases = json.loads(_CASES.read_text(encoding="utf-8"))
    runs: dict[str, dict] = {}
    for label, overrides in CONFIGS:
        runs[label] = await run_config(label, overrides, cases)

    aggs = {label: run["aggregate"] for label, run in runs.items() if not run["failed"]}
    if "baseline" in aggs:
        print("\n" + format_matrix(aggs, baseline="baseline"))

    _RESULTS_DIR.mkdir(exist_ok=True)
    out = _RESULTS_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
    payload = {
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "embedding": embedding_service.identity(),
        "cases": len(cases),
        "runs": runs,
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nResults written to {out}")


if __name__ == "__main__":
    asyncio.run(main())
