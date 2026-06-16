"""Run the retrieval eval against the live index. Requires Qdrant + an index.

Usage:
    cd backend && uv run --no-sync python -m evals.run_eval

Treat the first run as a baseline: per-case MISS results are signal (a retrieval gap
or a too-strict expectation), not test failures.
"""

import asyncio
import json
from pathlib import Path

from app.core.retriever import retriever
from app.services.vector import get_vector_store
from evals.harness import aggregate, score_case

_CASES = Path(__file__).parent / "cases.json"


async def main() -> None:
    store = get_vector_store()
    if not await store.health_check():
        await store.connect()

    cases = json.loads(_CASES.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        result = await retriever.retrieve(case["query"], case.get("edition"))
        chunks = [*result.authoritative, *result.examples]
        scored = score_case(chunks, case["expect"])
        results.append(scored)
        flag = "HIT " if scored["hit"] else "MISS"
        rank = str(scored["rank"]) if scored["rank"] is not None else "-"
        print(f"[{flag}] rank={rank:>3}  {case['id']}: {case['query']}")

    agg = aggregate(results)
    print(f"\n{agg['hits']}/{agg['cases']} hit ({agg['hit_rate']:.0%}), MRR={agg['mrr']:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
