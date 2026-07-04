"""Agent engine - orchestrates prompt construction and the tool-using agent loop.

Entry point for the chat pipeline. Retrieval is agent-driven: the MPMB
toolset (including `mpmb_search`) is attached when tool use is enabled,
and `Deps(session_id, edition)` is injected so tools can scope file
access per request. Nothing is pre-fetched on the request path.

Usage:
    response = await rag_engine.generate(
        query="How do I add a spell?",
        conversation_history=[...],
        session_id="uuid-here",
        edition="2014",
    )

    async for event in rag_engine.stream(query=..., session_id=...):
        if event.event == "tool_start":
            ...
"""

import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from pydantic_ai import Agent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)
from pydantic_ai.usage import UsageLimits

from app.core.agent import (
    LLMResponse,
    _extract_stop_reason_from_messages,
    _extract_usage,
    build_agent,
)
from app.core.agent import (
    generate as agent_generate,
)
from app.core.prompts import prompt_builder
from app.core.query_analysis import analyze_query
from app.core.tools import Deps, build_mpmb_toolset, wrap_with_budget
from app.logger import get_logger
from app.services.llm.messages import to_pydantic_messages
from app.services.source_catalog import source_catalog_service
from app.services.source_catalog.prompt_render import per_query_hints as _render_hints
from app.settings import settings

logger = get_logger(__name__)


# * Response types
@dataclass
class RAGResponse:
    content: str
    provider: str = ""
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    stop_reason: Optional[str] = None
    timing: dict[str, float] = field(default_factory=dict)
    tools: dict[str, Any] = field(default_factory=dict)
    retrieval: list[dict] = field(default_factory=list)


@dataclass
class RAGStreamEvent:
    content: str = ""
    done: bool = False
    provider: str = ""
    model: str = ""
    stop_reason: Optional[str] = None
    usage: Optional[dict[str, Any]] = None
    timing: Optional[dict[str, float]] = None
    event: Optional[str] = None
    tool: Optional[dict[str, Any]] = None
    tools: Optional[dict[str, Any]] = None
    retrieval: Optional[list[dict]] = None


# * Hard net for runaway loops; matches pydantic-ai's own default request_limit
_FALLBACK_REQUEST_LIMIT = 50

# ? Streamed to the user when even the hard net trips; the soft budget should fire first
TOOL_LIMIT_NOTICE = (
    "\n\nI hit my tool-call limit for this turn, so this answer is based on "
    "what I gathered before the cutoff. Ask a narrower follow-up if something is missing."
)


# * Helpers
def _resolve_tool_use(toolset_enabled: bool):
    if not toolset_enabled:
        return None, None
    budget = settings.max_tool_calls
    toolset = wrap_with_budget(build_mpmb_toolset(), budget=budget)
    # ! Soft cap returns a stop notice to the model; this hard net only catches stubborn loops
    request_limit = budget + 5 if budget and budget > 0 else _FALLBACK_REQUEST_LIMIT
    return toolset, UsageLimits(request_limit=request_limit)


def _derive_tool_status(result_text: str) -> str:
    if result_text.startswith("[error]"):
        return "error"
    if "[truncated" in result_text:
        return "truncated"
    return "success"


def _build_catalog_hints(qa, settings_ref) -> Optional[str]:
    """Construct per-query catalog hints from a QueryAnalysis."""
    object_type_match = None
    if qa is not None and qa.object_type:
        match = source_catalog_service.find_object_type(qa.object_type)
        if match is None:
            # Synthesize a minimal match so the hint still surfaces the resolved type
            from app.model.schemas.source_catalog import ObjectTypeMatch

            object_type_match = ObjectTypeMatch(
                object_type=qa.object_type,
                matched_via="code_identifier",
                matched_term=qa.object_type,
            )
        else:
            object_type_match = match

    matched_symbols: list = []
    # We don't have the symbol name in IntentResult today; v1 leaves matched_symbols empty.
    # Future: thread the matched symbol through IntentResult.

    # `health()` is async; per-request hint rendering needs a cheap sync read.
    # has_data() distinguishes HEALTHY/STALE (both ok) from MISSING/MALFORMED.
    # Known small gap: this collapses STALE -> HEALTHY for hint purposes, so the
    # spec's "stale-warning prefix" doesn't fire yet. Tracked in closeout follow-ups.
    from app.model.schemas.source_catalog import CatalogState

    catalog_state = CatalogState.HEALTHY if source_catalog_service.has_data() else CatalogState.MISSING

    return _render_hints(
        object_type_match=object_type_match,
        matched_symbols=matched_symbols,
        coverage_warnings=tuple(source_catalog_service.coverage_warnings()),
        catalog_state=catalog_state,
        injection_enabled=bool(getattr(settings_ref, "inject_catalog_context", True)),
    )


class RAGEngine:
    async def generate(
        self,
        query: str,
        conversation_history: Optional[list[dict]] = None,
        session_id: Optional[str] = None,
        edition: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> RAGResponse:
        t_start = time.perf_counter()

        # ! No pre-retrieval - the agent calls mpmb_search itself when needed
        analysis = analyze_query(query)
        resolved_edition = edition or analysis.edition or settings.default_edition

        catalog_hints = _build_catalog_hints(analysis, settings)
        user_prompt = prompt_builder.build_user_prompt(
            query=query,
            edition=resolved_edition,
            catalog_hints=catalog_hints,
        )

        toolset, usage_limits = _resolve_tool_use(settings.enable_tool_use)
        deps = Deps(session_id=session_id or "unknown", edition=resolved_edition) if toolset else None

        t_generate = time.perf_counter()
        try:
            llm_response = await agent_generate(
                instructions=prompt_builder.get_static_instructions(),
                user_prompt=user_prompt,
                history=conversation_history,
                provider=provider,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                toolset=toolset,
                deps=deps,
                usage_limits=usage_limits,
            )
        except UsageLimitExceeded as e:
            # ! Hard net tripped; return a best-effort notice instead of raising
            logger.warning(f"Tool-call hard limit hit during generate: {e}")
            llm_response = LLMResponse(
                content=TOOL_LIMIT_NOTICE.strip(),
                provider=provider or settings.default_llm_provider,
                model=model or settings.default_model,
                stop_reason="tool_budget_exceeded",
            )
        generation_ms = (time.perf_counter() - t_generate) * 1000
        total_ms = (time.perf_counter() - t_start) * 1000

        logger.info(
            f"Agent complete: {llm_response.usage.get('total_tokens', '?')} tokens, "
            f"gen={generation_ms:.0f}ms total={total_ms:.0f}ms"
        )

        return RAGResponse(
            content=llm_response.content,
            provider=llm_response.provider,
            model=llm_response.model,
            usage=llm_response.usage,
            stop_reason=llm_response.stop_reason,
            timing={
                "generation_ms": round(generation_ms, 1),
                "total_ms": round(total_ms, 1),
            },
            retrieval=deps.trace if deps else [],
        )

    async def stream(
        self,
        query: str,
        conversation_history: Optional[list[dict]] = None,
        session_id: Optional[str] = None,
        edition: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[RAGStreamEvent]:
        t_start = time.perf_counter()
        resolved_provider = provider or settings.default_llm_provider

        # ! No pre-retrieval - the agent calls mpmb_search itself when needed
        analysis = analyze_query(query)
        resolved_edition = edition or analysis.edition or settings.default_edition
        catalog_hints = _build_catalog_hints(analysis, settings)
        user_prompt = prompt_builder.build_user_prompt(
            query=query,
            edition=resolved_edition,
            catalog_hints=catalog_hints,
        )

        toolset, usage_limits = _resolve_tool_use(settings.enable_tool_use)
        deps = Deps(session_id=session_id or "unknown", edition=resolved_edition) if toolset else None

        agent: Agent = build_agent(
            instructions=prompt_builder.get_static_instructions(),
            provider=resolved_provider,
            model=model or settings.default_model,
            temperature=temperature,
            max_tokens=max_tokens,
            toolset=toolset,
        )
        pydantic_history = to_pydantic_messages(conversation_history or [])

        t_generate = time.perf_counter()
        tool_calls: list[dict[str, Any]] = []
        tool_start_times: dict[str, float] = {}
        # ? After a tool result, the model's next text part starts mid-sentence
        # ? with no separator. Inject a paragraph break before the first text
        # ? chunk that follows a tool_end so sentences don't collide.
        needs_separator = False

        run_kwargs: dict[str, Any] = {"message_history": pydantic_history}
        if deps is not None:
            run_kwargs["deps"] = deps
        if usage_limits is not None:
            run_kwargs["usage_limits"] = usage_limits

        limit_hit = False
        run = None
        try:
            async with agent.iter(user_prompt, **run_kwargs) as run:
                async for node in run:
                    if Agent.is_model_request_node(node):
                        async with node.stream(run.ctx) as request_stream:
                            async for event in request_stream:
                                text: str | None = None
                                if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                                    text = event.part.content
                                elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                                    text = event.delta.content_delta
                                if text:
                                    if needs_separator:
                                        text = "\n\n" + text.lstrip()
                                        needs_separator = False
                                    yield RAGStreamEvent(content=text)
                    elif Agent.is_call_tools_node(node):
                        async with node.stream(run.ctx) as handle_stream:
                            async for event in handle_stream:
                                if isinstance(event, FunctionToolCallEvent):
                                    name = event.part.tool_name
                                    call_id = event.part.tool_call_id
                                    tool_start_times[call_id] = time.perf_counter()
                                    yield RAGStreamEvent(
                                        event="tool_start",
                                        tool={"name": name},
                                    )
                                elif isinstance(event, FunctionToolResultEvent):
                                    call_id = event.tool_call_id
                                    t0 = tool_start_times.pop(call_id, time.perf_counter())
                                    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
                                    content = getattr(event.part, "content", "")
                                    name = getattr(event.part, "tool_name", "")
                                    status = _derive_tool_status(str(content))
                                    tool_calls.append({"name": name, "status": status, "duration_ms": duration_ms})
                                    yield RAGStreamEvent(
                                        event="tool_end",
                                        tool={"name": name, "status": status, "duration_ms": duration_ms},
                                    )
                                    needs_separator = True
        except UsageLimitExceeded as e:
            # ! Hard net tripped; degrade to a best-effort answer instead of an error chunk
            logger.warning(f"Tool-call hard limit hit during stream: {e}")
            limit_hit = True
            yield RAGStreamEvent(content=TOOL_LIMIT_NOTICE)

        generation_ms = (time.perf_counter() - t_generate) * 1000
        total_ms = (time.perf_counter() - t_start) * 1000

        final_result = run.result if run is not None else None
        if final_result:
            usage = _extract_usage(final_result.usage)
        elif run is not None:
            usage = _extract_usage(run.usage)
        else:
            usage = {}
        if limit_hit:
            stop_reason = "tool_budget_exceeded"
        else:
            stop_reason = _extract_stop_reason_from_messages(final_result.all_messages() if final_result else [])

        tools_meta = (
            {
                "total_calls": len(tool_calls),
                "calls": tool_calls,
            }
            if tool_calls
            else None
        )

        yield RAGStreamEvent(
            done=True,
            provider=resolved_provider,
            model=model or settings.default_model,
            stop_reason=stop_reason,
            usage=usage,
            timing={
                "generation_ms": round(generation_ms, 1),
                "total_ms": round(total_ms, 1),
            },
            tools=tools_meta,
            retrieval=deps.trace if deps else None,
        )


rag_engine = RAGEngine()
