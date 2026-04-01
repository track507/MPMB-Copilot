"""RAG engine - orchestrates retrieval, prompt construction, and LLM generation.

This is the main entry point for the chat pipeline.  It ties together:
    1. Retriever (tier-aware chunk retrieval)
    2. Prompt builder (static instructions + RAG context + history)
    3. LLM client (multi-provider generation with streaming)

The chat API endpoint calls `rag_engine.generate()` or
`rag_engine.stream()` - it doesn't need to know about the
retrieval or prompt internals.

Usage:
    from app.core.rag_engine import rag_engine

    # Non-streaming
    response = await rag_engine.generate(
        query="How do I add a spell?",
        conversation_history=[...],
        edition="2014",
    )
    print(response.content)
    print(response.retrieval_info)

    # Streaming
    async for event in rag_engine.stream(
        query="Write me a feat",
        conversation_history=[],
    ):
        print(event.content, end="", flush=True)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from app.core.prompts import prompt_builder
from app.core.retriever import retriever
from app.services.llm_client import llm_client
from app.settings import settings

logger = logging.getLogger(__name__)


# * Response types
@dataclass
class RAGResponse:
    """Complete response from the RAG pipeline."""

    content: str
    """Generated text from the LLM."""

    provider: str = ""
    """LLM provider used."""

    model: str = ""
    """LLM model used."""

    usage: dict[str, Any] = field(default_factory=dict)
    """Token usage including cache details."""

    stop_reason: Optional[str] = None
    """Why generation stopped."""

    retrieval_info: dict[str, Any] = field(default_factory=dict)
    """Retrieval metadata (intent, tier counts, timing)."""

    timing: dict[str, float] = field(default_factory=dict)
    """Timing breakdown: retrieval_ms, generation_ms, total_ms."""


@dataclass
class RAGStreamEvent:
    """Single event from a streaming RAG response."""

    content: str = ""
    """Incremental text chunk."""

    done: bool = False
    """True when the stream is complete."""

    usage: Optional[dict[str, Any]] = None
    """Token usage - final event only."""

    retrieval_info: Optional[dict[str, Any]] = None
    """Retrieval metadata - final event only."""

    timing: Optional[dict[str, float]] = None
    """Timing breakdown - final event only."""


# * Engine
class RAGEngine:
    """Orchestrates the full RAG pipeline: retrieve -> prompt -> generate."""

    async def generate(
        self,
        query: str,
        conversation_history: Optional[list[dict]] = None,
        edition: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> RAGResponse:
        """Run the full RAG pipeline and return a complete response.

        Args:
            query: User's question.
            conversation_history: Previous messages as dicts with
                'role' and 'content' keys (from session DB).
            edition: Force edition ('2014' or '2024').
            provider: Override LLM provider.
            model: Override LLM model.
            temperature: Override temperature.
            max_tokens: Override max tokens.

        Returns:
            RAGResponse with content, usage, retrieval info, and timing.
        """
        t_start = time.perf_counter()
        resolved_provider = provider or settings.default_llm_provider

        # 1. Retrieve relevant chunks
        t_retrieve = time.perf_counter()
        retrieval_result = await retriever.retrieve(
            query=query,
            edition=edition,
        )
        retrieval_ms = (time.perf_counter() - t_retrieve) * 1000

        # 2. Resolve edition (explicit > retriever-inferred > settings default)
        resolved_edition = (
            edition
            or (retrieval_result.query_analysis.edition if retrieval_result.query_analysis else None)
            or settings.default_edition
        )

        # 3. Build messages with prompt caching
        messages = prompt_builder.build_messages(
            query=query,
            retrieval_result=retrieval_result,
            conversation_history=conversation_history,
            edition=resolved_edition,
            provider=resolved_provider,
        )

        # 4. Generate LLM response
        t_generate = time.perf_counter()
        llm_response = await llm_client.generate(
            messages=messages,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        generation_ms = (time.perf_counter() - t_generate) * 1000

        total_ms = (time.perf_counter() - t_start) * 1000

        retrieval_info = retrieval_result.to_dict()

        logger.info(
            f"RAG complete: {retrieval_result.total_chunks} chunks, "
            f"{llm_response.usage.get('total_tokens', '?')} tokens, "
            f"retrieve={retrieval_ms:.0f}ms gen={generation_ms:.0f}ms "
            f"total={total_ms:.0f}ms"
        )

        return RAGResponse(
            content=llm_response.content,
            provider=llm_response.provider,
            model=llm_response.model,
            usage=llm_response.usage,
            stop_reason=llm_response.stop_reason,
            retrieval_info=retrieval_info,
            timing={
                "retrieval_ms": round(retrieval_ms, 1),
                "generation_ms": round(generation_ms, 1),
                "total_ms": round(total_ms, 1),
            },
        )

    async def stream(
        self,
        query: str,
        conversation_history: Optional[list[dict]] = None,
        edition: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[RAGStreamEvent]:
        """Run the RAG pipeline and stream the response.

        Retrieval happens first (not streamed), then the LLM response
        streams incrementally.  The final event includes usage and
        retrieval metadata.

        Yields:
            RAGStreamEvent objects.  `done=True` on the last event.
        """
        t_start = time.perf_counter()
        resolved_provider = provider or settings.default_llm_provider

        # 1. Retrieve (blocking - must complete before generation starts)
        t_retrieve = time.perf_counter()
        retrieval_result = await retriever.retrieve(
            query=query,
            edition=edition,
        )
        retrieval_ms = (time.perf_counter() - t_retrieve) * 1000

        # 2. Resolve edition
        resolved_edition = (
            edition
            or (retrieval_result.query_analysis.edition if retrieval_result.query_analysis else None)
            or settings.default_edition
        )

        # 3. Build messages
        messages = prompt_builder.build_messages(
            query=query,
            retrieval_result=retrieval_result,
            conversation_history=conversation_history,
            edition=resolved_edition,
            provider=resolved_provider,
        )

        # 4. Stream LLM response
        t_generate = time.perf_counter()

        async for event in llm_client.stream(
            messages=messages,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if event.done:
                # Final event - attach all metadata
                generation_ms = (time.perf_counter() - t_generate) * 1000
                total_ms = (time.perf_counter() - t_start) * 1000

                yield RAGStreamEvent(
                    content="",
                    done=True,
                    usage=event.usage,
                    retrieval_info=retrieval_result.to_dict(),
                    timing={
                        "retrieval_ms": round(retrieval_ms, 1),
                        "generation_ms": round(generation_ms, 1),
                        "total_ms": round(total_ms, 1),
                    },
                )
            else:
                yield RAGStreamEvent(content=event.content)


# * Global instance
rag_engine = RAGEngine()
