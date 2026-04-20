"""RAG engine - orchestrates retrieval, prompt construction, and LLM generation.

Entry point for the chat pipeline. When tool use is enabled, the MPMB
toolset is attached to the agent and `Deps(session_id, edition)` is
injected so tools can scope file access per request.

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
    _extract_stop_reason_from_messages,
    _extract_usage,
    build_agent,
)
from app.core.agent import (
    generate as agent_generate,
)
from app.core.prompts import prompt_builder
from app.core.retriever import retriever
from app.core.tools import Deps, build_mpmb_toolset
from app.logger import get_logger
from app.services.llm.messages import to_pydantic_messages
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
    retrieval_info: dict[str, Any] = field(default_factory=dict)
    timing: dict[str, float] = field(default_factory=dict)
    tools: dict[str, Any] = field(default_factory=dict)


@dataclass
class RAGStreamEvent:
    content: str = ""
    done: bool = False
    provider: str = ""
    model: str = ""
    stop_reason: Optional[str] = None
    usage: Optional[dict[str, Any]] = None
    retrieval_info: Optional[dict[str, Any]] = None
    timing: Optional[dict[str, float]] = None
    event: Optional[str] = None
    tool: Optional[dict[str, Any]] = None
    tools: Optional[dict[str, Any]] = None


# * Helpers
def _resolve_tool_use(toolset_enabled: bool):
    if not toolset_enabled:
        return None, None
    toolset = build_mpmb_toolset()
    usage_limits = None
    if settings.max_tool_calls and settings.max_tool_calls > 0:
        usage_limits = UsageLimits(request_limit=settings.max_tool_calls)
    return toolset, usage_limits


def _derive_tool_status(result_text: str) -> str:
    if result_text.startswith("[error]"):
        return "error"
    if "[truncated" in result_text:
        return "truncated"
    return "success"


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

        t_retrieve = time.perf_counter()
        retrieval_result = await retriever.retrieve(query=query, edition=edition)
        retrieval_ms = (time.perf_counter() - t_retrieve) * 1000

        resolved_edition = (
            edition
            or (retrieval_result.query_analysis.edition if retrieval_result.query_analysis else None)
            or settings.default_edition
        )

        user_prompt = prompt_builder.build_user_prompt(
            query=query,
            retrieval_result=retrieval_result,
            edition=resolved_edition,
        )

        toolset, usage_limits = _resolve_tool_use(settings.enable_tool_use)
        deps = Deps(session_id=session_id or "unknown", edition=resolved_edition) if toolset else None

        t_generate = time.perf_counter()
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
        generation_ms = (time.perf_counter() - t_generate) * 1000
        total_ms = (time.perf_counter() - t_start) * 1000

        logger.info(
            f"RAG complete: {retrieval_result.total_chunks} chunks, "
            f"{llm_response.usage.get('total_tokens', '?')} tokens, "
            f"retrieve={retrieval_ms:.0f}ms gen={generation_ms:.0f}ms total={total_ms:.0f}ms"
        )

        return RAGResponse(
            content=llm_response.content,
            provider=llm_response.provider,
            model=llm_response.model,
            usage=llm_response.usage,
            stop_reason=llm_response.stop_reason,
            retrieval_info=retrieval_result.to_dict(),
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
        session_id: Optional[str] = None,
        edition: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[RAGStreamEvent]:
        t_start = time.perf_counter()
        resolved_provider = provider or settings.default_llm_provider

        t_retrieve = time.perf_counter()
        retrieval_result = await retriever.retrieve(query=query, edition=edition)
        retrieval_ms = (time.perf_counter() - t_retrieve) * 1000

        resolved_edition = (
            edition
            or (retrieval_result.query_analysis.edition if retrieval_result.query_analysis else None)
            or settings.default_edition
        )
        user_prompt = prompt_builder.build_user_prompt(
            query=query,
            retrieval_result=retrieval_result,
            edition=resolved_edition,
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

        run_kwargs: dict[str, Any] = {"message_history": pydantic_history}
        if deps is not None:
            run_kwargs["deps"] = deps
        if usage_limits is not None:
            run_kwargs["usage_limits"] = usage_limits

        async with agent.iter(user_prompt, **run_kwargs) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    async with node.stream(run.ctx) as request_stream:
                        async for event in request_stream:
                            if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                                if event.part.content:
                                    yield RAGStreamEvent(content=event.part.content)
                            elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                                if event.delta.content_delta:
                                    yield RAGStreamEvent(content=event.delta.content_delta)
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
                                content = getattr(event.result, "content", "")
                                name = getattr(event.result, "tool_name", "")
                                status = _derive_tool_status(str(content))
                                tool_calls.append({"name": name, "status": status, "duration_ms": duration_ms})
                                yield RAGStreamEvent(
                                    event="tool_end",
                                    tool={"name": name, "status": status, "duration_ms": duration_ms},
                                )

        generation_ms = (time.perf_counter() - t_generate) * 1000
        total_ms = (time.perf_counter() - t_start) * 1000

        final_result = run.result
        usage = _extract_usage(final_result.usage()) if final_result else {}
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
            retrieval_info=retrieval_result.to_dict(),
            timing={
                "retrieval_ms": round(retrieval_ms, 1),
                "generation_ms": round(generation_ms, 1),
                "total_ms": round(total_ms, 1),
            },
            tools=tools_meta,
        )


rag_engine = RAGEngine()
