import pytest

from app.core.tools.budget import BUDGET_EXHAUSTED_MSG, ToolBudgetToolset, wrap_with_budget


class FakeToolset:
    """Records calls; stands in for the wrapped MPMB toolset."""

    def __init__(self):
        self.calls = []

    async def call_tool(self, name, tool_args, ctx, tool):
        self.calls.append((name, tool_args))
        return f"ran {name}"


@pytest.mark.asyncio
async def test_under_budget_delegates_to_wrapped():
    fake = FakeToolset()
    ts = ToolBudgetToolset(wrapped=fake, budget=2)

    result = await ts.call_tool("mpmb_read", {"path": "a.js"}, None, None)

    assert result == "ran mpmb_read"
    assert ts.calls_made == 1
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_over_budget_returns_notice_without_executing():
    fake = FakeToolset()
    ts = ToolBudgetToolset(wrapped=fake, budget=1)

    await ts.call_tool("mpmb_read", {}, None, None)
    result = await ts.call_tool("mpmb_grep", {}, None, None)

    assert result == BUDGET_EXHAUSTED_MSG.format(budget=1)
    assert len(fake.calls) == 1
    assert ts.calls_made == 1


@pytest.mark.asyncio
async def test_over_budget_notice_repeats_on_every_refusal():
    fake = FakeToolset()
    ts = ToolBudgetToolset(wrapped=fake, budget=1)

    await ts.call_tool("mpmb_read", {}, None, None)
    first_refusal = await ts.call_tool("mpmb_grep", {}, None, None)
    second_refusal = await ts.call_tool("mpmb_function", {}, None, None)

    assert first_refusal == second_refusal
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_budget_zero_disables_soft_cap():
    fake = FakeToolset()
    ts = ToolBudgetToolset(wrapped=fake, budget=0)

    for _ in range(20):
        await ts.call_tool("mpmb_read", {}, None, None)

    assert len(fake.calls) == 20


def test_wrap_with_budget_returns_fresh_instance():
    fake = FakeToolset()

    first = wrap_with_budget(fake, budget=3)
    second = wrap_with_budget(fake, budget=3)

    assert first is not second
    assert first.budget == 3
    assert first.calls_made == 0
