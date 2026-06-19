"""
Run the retrieval eval against the live index
Requires Qdrant + an index

Usage:
    cd backend && uv run --no-sync python -m evals.run_eval

Treat the first run as a baseline: per-case MISS results are signal (a retrieval gap or a too-strict expectation), not test failures
"""

import asyncio
import json
from pathlib import Path

from app.core.retriever import retriever
from app.services.vector import get_vector_store
from app.settings import settings
from evals.harness import aggregate, format_comparison, score_case

_CASES = Path(__file__).parent / "cases.json"


async def main() -> None:
    store = get_vector_store()
    if not await store.health_check():
        await store.connect()

    cases = json.loads(_CASES.read_text(encoding="utf-8"))

    aggs: dict[str, dict] = {}
    for label, flag in (("baseline", False), ("reranked", True)):
        settings.rerank_enabled = flag  # ? in-process toggle; this is a throwaway script run
        print(f"\n=== {label} (rerank {'on' if flag else 'off'}) ===")
        results = []
        for case in cases:
            result = await retriever.retrieve(case["query"], case.get("edition"))
            chunks = [*result.authoritative, *result.examples]
            scored = score_case(chunks, case["expect"])
            results.append(scored)
            mark = "HIT " if scored["hit"] else "MISS"
            rank = str(scored["rank"]) if scored["rank"] is not None else "-"
            print(f"[{mark}] rank={rank:>3}  {case['id']}: {case['query']}")
        aggs[label] = aggregate(results)

    print("\n" + format_comparison(aggs["baseline"], aggs["reranked"]))


if __name__ == "__main__":
    asyncio.run(main())
