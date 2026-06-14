"""Query intent classification for retrieval routing.

Classifies user queries into intents (how_to, generate, debug, lookup)
to determine retrieval tier budgets.  Three classification layers run
in order:

1. **Symbol detection** - fast regex scan for MPMB code identifiers
        (`AddSubClass`, `SpellsList`, etc.).  Language-agnostic because
        these are code tokens, not natural language.

2. **Embedding classification** - compares the query embedding (already
        computed for vector search) against pre-computed intent centroids.
        Language-agnostic because embeddings capture semantics across languages.

3. **Confidence gating** - if the margin between top-2 intents is below
        threshold, returns a blended result so the retriever broadens its
        search.  Low-confidence events are logged for tuning.

Usage:
    from app.core.intent import intent_classifier

    result = intent_classifier.classify(
        query="How do I add a spell?",
        query_embedding=[0.1, 0.2, ...],
    )
    result.primary    # QueryIntent.HOW_TO
    result.confidence # 0.72
    result.is_blended # False
"""

import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from app.logger import get_logger
from app.services.source_catalog import source_catalog_service
from app.settings import settings as dynamic_settings

logger = get_logger(__name__)


# * Intent enum
class QueryIntent(str, Enum):
    """Query intent categories that drive retrieval profiles."""

    HOW_TO = "how_to"
    """Beginner questions: "How do I add a spell?" """

    GENERATE = "generate"
    """Code generation: "Write me a feat for heavy armor" """

    DEBUG = "debug"
    """Troubleshooting: "My subclass features aren't showing up" """

    LOOKUP = "lookup"
    """Reference lookup: "What does AddSubClass do?" """


# * Classification result
@dataclass(frozen=True)
class IntentResult:
    """Result of intent classification."""

    primary: QueryIntent
    """Highest-confidence intent."""

    secondary: Optional[QueryIntent]
    """Second-highest intent (always populated unless only one intent exists)."""

    confidence: float
    """Cosine similarity of primary intent (0.0-1.0).
    Below `intent_confidence_threshold` means the classifier is guessing."""

    margin: float
    """Gap between primary and secondary similarity scores.
    Below `intent_confidence_margin` triggers blending."""

    is_blended: bool
    """True when margin is too small to confidently pick one intent.
    The retriever should merge the tier budgets of both intents."""

    method: str
    """Which layer determined the result: 'symbol', 'embedding', or 'fallback'."""


# * Error-adjacent patterns override symbol detection -> debug
_ERROR_CONTEXT_PATTERN = re.compile(
    r"\b(error|bug|crash|fail|broken|not\s+work|won.t\s+load|doesn.t\s+show)\b",
    re.IGNORECASE,
)


def _detect_symbol_intent(query: str) -> Optional[tuple[QueryIntent, str]]:
    """
    Catalog-backed symbol detection

    Returns None when the catalog is missing/malformed (Layer 1 skipped)
    All catalog-derived symbols map to LOOKUP unless _ERROR_CONTEXT_PATTERN matches, in which case DEBUG wins
    """
    symbol_index = source_catalog_service.symbol_index()
    if not symbol_index:
        return None

    for symbol in sorted(symbol_index, key=len, reverse=True):
        if re.search(rf"\b{re.escape(symbol)}\b", query):
            if _ERROR_CONTEXT_PATTERN.search(query):
                return (QueryIntent.DEBUG, symbol)
            return (QueryIntent.LOOKUP, symbol)
    return None


# * Embedding classification (Layer 2)
def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class _CentroidStore:
    """Lazily computes and caches intent centroids from example queries.

    Centroids are the mean embedding of example queries for each intent.
    They're computed once on first use and recomputed if the examples
    file changes.
    """

    def __init__(self):
        self._centroids: Optional[dict[QueryIntent, list[float]]] = None
        self._examples_path: Optional[Path] = None
        self._examples_mtime: float = 0.0

    def _resolve_path(self) -> Path:
        """Find the intent examples file."""
        if self._examples_path is not None:
            return self._examples_path

        # Check common locations
        candidates = [
            Path("data/intent_examples.json"),
            Path("./data/intent_examples.json"),
            Path(__file__).parent.parent.parent.parent / "data" / "intent_examples.json",
        ]

        for path in candidates:
            if path.exists():
                self._examples_path = path
                return path

        raise FileNotFoundError("Intent examples file not found. Expected at data/intent_examples.json")

    def _needs_recompute(self) -> bool:
        """Check if centroids need recomputing (file changed or not yet computed)."""
        if self._centroids is None:
            return True

        try:
            path = self._resolve_path()
            current_mtime = path.stat().st_mtime
            return current_mtime != self._examples_mtime
        except FileNotFoundError:
            return self._centroids is None

    def get_centroids(self) -> dict[QueryIntent, list[float]]:
        """Return intent centroids, computing them if necessary."""
        if not self._needs_recompute():
            return self._centroids

        self._centroids = self._compute_centroids()
        return self._centroids

    def _compute_centroids(self) -> dict[QueryIntent, list[float]]:
        """Load examples, embed them, average per intent."""
        from app.services.embedding import embedding_service

        path = self._resolve_path()
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._examples_mtime = path.stat().st_mtime

        centroids: dict[QueryIntent, list[float]] = {}

        for intent_name, examples in raw.items():
            try:
                intent = QueryIntent(intent_name)
            except ValueError:
                logger.warning(f"Unknown intent in examples file: {intent_name}")
                continue

            if not examples:
                continue

            # Embed all examples for this intent (query prefix, to match the query embedding they're compared against)
            embeddings = [embedding_service.embed_query(example) for example in examples]

            # Compute mean (centroid)
            dim = len(embeddings[0])
            centroid = [0.0] * dim
            for emb in embeddings:
                for i, val in enumerate(emb):
                    centroid[i] += val
            centroid = [v / len(embeddings) for v in centroid]

            centroids[intent] = centroid
            logger.debug(f"Intent centroid '{intent_name}': {len(examples)} examples -> {dim}d centroid")

        logger.info(
            f"Computed {len(centroids)} intent centroids from {path.name} "
            f"({sum(len(raw.get(i.value, [])) for i in QueryIntent)} total examples)"
        )

        return centroids


_centroid_store = _CentroidStore()


def _classify_by_embedding(
    query_embedding: list[float],
) -> tuple[list[tuple[QueryIntent, float]], str]:
    """Classify intent by cosine similarity to centroids.

    Returns sorted list of (intent, similarity) pairs (highest first)
    and the method name.
    """
    try:
        centroids = _centroid_store.get_centroids()
    except FileNotFoundError:
        logger.warning("No intent examples file - falling back to HOW_TO")
        return [(QueryIntent.HOW_TO, 0.0)], "fallback"

    if not centroids:
        return [(QueryIntent.HOW_TO, 0.0)], "fallback"

    scores = [(intent, _cosine_similarity(query_embedding, centroid)) for intent, centroid in centroids.items()]
    scores.sort(key=lambda x: x[1], reverse=True)

    return scores, "embedding"


# * Public API
class IntentClassifier:
    """Stateless intent classifier combining symbol detection and embedding similarity."""

    def classify(
        self,
        query: str,
        query_embedding: list[float],
        intent_override: Optional[str] = None,
    ) -> IntentResult:
        """Classify query intent.

        Args:
            query: Raw query text.
            query_embedding: Pre-computed dense embedding of the query.
            intent_override: Force a specific intent (bypasses classification).

        Returns:
            IntentResult with primary/secondary intent, confidence, and blend flag.
        """
        # Manual override
        if intent_override:
            try:
                forced = QueryIntent(intent_override)
                return IntentResult(
                    primary=forced,
                    secondary=None,
                    confidence=1.0,
                    margin=1.0,
                    is_blended=False,
                    method="override",
                )
            except ValueError:
                logger.warning(f"Invalid intent override: {intent_override}")

        method = dynamic_settings.intent_method

        # Layer 1: Symbol detection (always runs in hybrid mode)
        if method in ("rule", "hybrid"):
            symbol_result = _detect_symbol_intent(query)
            if symbol_result:
                intent, symbol = symbol_result
                logger.debug(f"Symbol detection: '{symbol}' -> {intent.value}")
                return IntentResult(
                    primary=intent,
                    secondary=None,
                    confidence=1.0,
                    margin=1.0,
                    is_blended=False,
                    method="symbol",
                )

        # Layer 2: Embedding classification
        if method in ("embedding", "hybrid"):
            scores, classify_method = _classify_by_embedding(query_embedding)

            if len(scores) < 2:
                primary = scores[0] if scores else (QueryIntent.HOW_TO, 0.0)
                return IntentResult(
                    primary=primary[0],
                    secondary=None,
                    confidence=primary[1],
                    margin=1.0,
                    is_blended=False,
                    method=classify_method,
                )

            primary_intent, primary_score = scores[0]
            secondary_intent, secondary_score = scores[1]
            margin = primary_score - secondary_score

            threshold = dynamic_settings.intent_confidence_threshold
            margin_threshold = dynamic_settings.intent_confidence_margin

            # Confidence gating
            is_blended = False
            if primary_score < threshold:
                logger.info(
                    f"Low intent confidence: {primary_intent.value}={primary_score:.3f} "
                    f"(threshold={threshold}). Falling back to how_to."
                )
                primary_intent = QueryIntent.HOW_TO
                is_blended = True
            elif margin < margin_threshold:
                logger.info(
                    f"Narrow intent margin: {primary_intent.value}={primary_score:.3f} vs "
                    f"{secondary_intent.value}={secondary_score:.3f} "
                    f"(margin={margin:.3f} < {margin_threshold}). Blending."
                )
                is_blended = True

            return IntentResult(
                primary=primary_intent,
                secondary=secondary_intent,
                confidence=primary_score,
                margin=margin,
                is_blended=is_blended,
                method=classify_method,
            )

        # Rule-only mode with no symbol match -> fallback
        return IntentResult(
            primary=QueryIntent.HOW_TO,
            secondary=None,
            confidence=0.0,
            margin=0.0,
            is_blended=True,
            method="fallback",
        )


# Global instance
intent_classifier = IntentClassifier()
