"""
Soft tool-call budget for the agent loop

Wraps the MPMB toolset and counts calls per run
Once the budget is spent, tools return a stop notice instead of executing, so the model can still produce a final answer
This avoids `UsageLimitExceeded` killing the stream when the model over-uses tools
"""

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.toolsets import AbstractToolset, WrapperToolset
from pydantic_ai.toolsets.abstract import ToolsetTool

from app.logger import get_logger
from app.settings import settings

logger = get_logger(__name__)

BUDGET_EXHAUSTED_MSG = (
    "[budget] Tool-call budget reached ({budget} calls this turn). "
    "Do not call any more tools. Answer the user now using the "
    "information already gathered. If it is insufficient, say what is "
    "missing and suggest a narrower follow-up question."
)


@dataclass
class ToolBudgetToolset(WrapperToolset[Any]):
    """Per-request soft cap on tool calls.

    Construct a fresh instance per chat request - the call counter is
    instance state and must not be shared across runs.
    """

    budget: int = 12
    calls_made: int = field(default=0, repr=False)

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        tool: ToolsetTool[Any],
    ) -> Any:
        # ! budget <= 0 disables the soft cap (hard net in rag_engine still applies)
        if self.budget > 0 and self.calls_made >= self.budget:
            logger.warning(f"tool.budget_exhausted name={name} budget={self.budget}")
            return BUDGET_EXHAUSTED_MSG.format(budget=self.budget)
        self.calls_made += 1
        return cap_result(await super().call_tool(name, tool_args, ctx, tool), settings.tool_result_max_bytes)


def cap_result(result: Any, max_bytes: int) -> Any:
    """
    A text result cut to max_bytes of UTF-8 with a note saying so; anything else unchanged

    max_bytes <= 0 disables the cap
    """
    if not isinstance(result, str) or max_bytes <= 0:
        return result
    encoded = result.encode("utf-8")
    if len(encoded) <= max_bytes:
        return result
    # ! errors="ignore" drops a character cut in half at the boundary instead of raising
    kept = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return (
        f"{kept}\n[truncated: showing the first {max_bytes} of {len(encoded)} bytes; "
        "narrow the request with a line range or a tighter pattern]"
    )


def wrap_with_budget(toolset: AbstractToolset[Any], budget: int) -> ToolBudgetToolset:
    """Wrap `toolset` in a fresh per-request budget enforcer."""
    return ToolBudgetToolset(wrapped=toolset, budget=budget)
