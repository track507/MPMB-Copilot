"""Tier-aware RAG retriever for MPMB code assistance.

Retrieves relevant code chunks from the vector store, grouping results
into authoritative (syntax/engine) and example (imports/community)
buckets.  The retriever detects query intent and adjusts the tier
balance accordingly.

Design principles:
    - Authoritative chunks answer "what is valid"
    - Example chunks answer "how people actually build it"
    - Most answers should combine both tiers
    - Intent determines the tier balance
    - Edition and object type narrow the search via metadata filters

Usage:
    from app.core.retriever import retriever

    result = await retriever.retrieve("How do I add a custom spell?")
    result.authoritative   # syntax templates, engine functions
    result.examples        # real spell implementations from imports
    result.query_analysis  # detected intent, edition, object_type
    result.timing_ms       # total retrieval time

    # With explicit overrides:
    result = await retriever.retrieve(
        query="write me a feat",
        edition="2024",
        intent_override="generate",
    )
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from app.core.intent import IntentResult, intent_classifier
from app.core.query_analysis import QueryAnalysis, analyze_query
from app.services.embeddings import embedding_service
from app.services.vector_store import get_vector_store
from app.settings import settings

logger = logging.getLogger(__name__)


# * Result types
@dataclass
class RetrievalResult:
    """Structured retrieval output with tier-grouped chunks."""

    authoritative: list[dict] = field(default_factory=list)
    """Syntax templates, engine functions - "what is valid"."""

    examples: list[dict] = field(default_factory=list)
    """Official and community examples - "how people build it"."""

    intent: IntentResult = field(default=None)
    """Detected intent with confidence and blend info."""

    query_analysis: QueryAnalysis = field(default=None)
    """Inferred edition, object type, function name."""

    timing_ms: float = 0.0
    """Total retrieval time in milliseconds."""

    @property
    def total_chunks(self) -> int:
        return len(self.authoritative) + len(self.examples)

    @property
    def is_empty(self) -> bool:
        return self.total_chunks == 0

    def to_dict(self) -> dict:
        """Serialize for API responses and logging."""
        return {
            "authoritative_count": len(self.authoritative),
            "examples_count": len(self.examples),
            "total_chunks": self.total_chunks,
            "intent": self.intent.primary.value if self.intent else None,
            "intent_confidence": self.intent.confidence if self.intent else None,
            "intent_blended": self.intent.is_blended if self.intent else None,
            "edition": self.query_analysis.edition if self.query_analysis else None,
            "object_type": self.query_analysis.object_type if self.query_analysis else None,
            "timing_ms": round(self.timing_ms, 1),
        }


# * Retriever
class Retriever:
    """Tier-aware retriever with intent-based budgets.

    Runs two filtered hybrid searches (authoritative + examples) and
    returns structured, deduplicated results grouped by source tier.
    """

    async def retrieve(
        self,
        query: str,
        edition: Optional[str] = None,
        intent_override: Optional[str] = None,
    ) -> RetrievalResult:
        """Retrieve relevant MPMB code chunks for a query.

        Args:
            query: Natural language query from the user.
            edition: Force edition filter ('2014' or '2024').
                                        If None, inferred from query or left unfiltered.
            intent_override: Force an intent (bypasses classification).

        Returns:
            RetrievalResult with tier-grouped chunks and analysis metadata.
        """
        t0 = time.perf_counter()

        # 1. Embed the query (reused for both search and intent classification)
        query_embedding = self._embed_query(query)

        # 2. Analyze the query for metadata signals
        analysis = analyze_query(query)

        # 3. Classify intent (reuses the query embedding - zero extra cost)
        intent = intent_classifier.classify(
            query=query,
            query_embedding=query_embedding,
            intent_override=intent_override,
        )

        # 4. Resolve edition (explicit > inferred > default)
        resolved_edition = edition or analysis.edition

        # 5. Build filters
        filters = self._build_filters(analysis, resolved_edition)

        # 6. Get tier budgets based on intent
        budget = self._resolve_budget(intent)

        # 7. Execute retrieval (single or dual based on settings)
        mode = settings.retrieval_mode

        if mode == "single":
            authoritative, examples = await self._single_search(
                query,
                query_embedding,
                filters,
                budget,
            )
        elif mode == "dual":
            authoritative, examples = await self._dual_search(
                query,
                query_embedding,
                filters,
                budget,
            )
        else:  # auto
            # Use dual when we have a clear intent, single otherwise
            if intent.confidence > settings.intent_confidence_threshold:
                authoritative, examples = await self._dual_search(
                    query,
                    query_embedding,
                    filters,
                    budget,
                )
            else:
                authoritative, examples = await self._single_search(
                    query,
                    query_embedding,
                    filters,
                    budget,
                )

        timing_ms = (time.perf_counter() - t0) * 1000

        result = RetrievalResult(
            authoritative=authoritative,
            examples=examples,
            intent=intent,
            query_analysis=analysis,
            timing_ms=timing_ms,
        )

        logger.info(
            f"Retrieved {result.total_chunks} chunks "
            f"({len(authoritative)} auth + {len(examples)} ex) "
            f"intent={intent.primary.value} conf={intent.confidence:.2f} "
            f"mode={mode} "
            f"in {timing_ms:.0f}ms"
        )

        return result

    # * Search strategies
    async def _dual_search(
        self,
        query: str,
        query_embedding: list[float],
        base_filters: dict,
        budget: dict[str, int],
    ) -> tuple[list[dict], list[dict]]:
        """Two separate searches: one for authoritative, one for examples.

        Guarantees both tiers are represented in results.
        """
        store = get_vector_store()

        auth_limit = budget.get("authoritative", 3)
        ex_limit = budget.get("examples", 5)

        # Authoritative search
        auth_filters = {**base_filters, "source_tier": "authoritative"}
        authoritative = await store.hybrid_search(
            query_text=query,
            query_embedding=query_embedding,
            filters=auth_filters,
            limit=auth_limit,
        )

        # Examples search (official + community)
        ex_filters = {
            **base_filters,
            "source_tier": ["official_example", "community_example"],
        }
        examples = await store.hybrid_search(
            query_text=query,
            query_embedding=query_embedding,
            filters=ex_filters,
            limit=ex_limit,
        )

        # Deduplicate (shouldn't happen with tier filters, but defensive)
        examples = self._deduplicate(examples, seen_ids={r["id"] for r in authoritative})

        return authoritative, examples

    async def _single_search(
        self,
        query: str,
        query_embedding: list[float],
        base_filters: dict,
        budget: dict[str, int],
    ) -> tuple[list[dict], list[dict]]:
        """One search, then split results by tier.

        Simpler but can't guarantee tier balance.
        """
        store = get_vector_store()
        total_limit = budget.get("authoritative", 3) + budget.get("examples", 5)

        all_results = await store.hybrid_search(
            query_text=query,
            query_embedding=query_embedding,
            filters=base_filters,
            limit=total_limit,
        )

        # Split by tier
        authoritative = [r for r in all_results if r.get("source_tier") == "authoritative"]
        examples = [r for r in all_results if r.get("source_tier") != "authoritative"]

        return authoritative, examples

    # * Helpers
    def _embed_query(self, query: str) -> list[float]:
        """Embed the query text using the configured embedding service."""
        embeddings = embedding_service.embed_texts([query])
        return embeddings[0]

    def _build_filters(
        self,
        analysis: QueryAnalysis,
        edition: Optional[str],
    ) -> dict:
        """Build metadata filters from query analysis.

        Only includes filters when we have high-confidence signals.
        Over-filtering on wrong metadata is worse than no filtering.
        """
        filters: dict = {}

        if edition:
            filters["edition"] = edition

        if analysis.object_type:
            filters["object_type"] = analysis.object_type

        if analysis.function_name:
            filters["function_name"] = analysis.function_name

        return filters

    def _resolve_budget(self, intent: IntentResult) -> dict[str, int]:
        """Look up tier budgets for the detected intent.

        If blended, merge the budgets of both intents (take the max
        of each tier to broaden the search).
        """
        primary_budget = settings.get_tier_budget(intent.primary.value)

        if not intent.is_blended or intent.secondary is None:
            return primary_budget

        secondary_budget = settings.get_tier_budget(intent.secondary.value)

        return {
            "authoritative": max(
                primary_budget.get("authoritative", 3),
                secondary_budget.get("authoritative", 3),
            ),
            "examples": max(
                primary_budget.get("examples", 5),
                secondary_budget.get("examples", 5),
            ),
        }

    def _deduplicate(
        self,
        results: list[dict],
        seen_ids: Optional[set] = None,
    ) -> list[dict]:
        """Remove duplicate chunks by ID, preserving order."""
        seen = seen_ids or set()
        deduped = []
        for result in results:
            rid = result.get("id")
            if rid and rid not in seen:
                seen.add(rid)
                deduped.append(result)
        return deduped


# * Global instance
retriever = Retriever()
