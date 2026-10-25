import pytest

from app.core.tools.budget import BUDGET_EXHAUSTED_MSG, ToolBudgetToolset, cap_result, wrap_with_budget


class FakeToolset:
    """Records calls; stands in for the wrapped MPMB toolset."""

    def __init__(self):
        self.calls = []

    async def call_tool(self, name, tool_args, ctx, tool):
        self.calls.append((name, tool_args))
        return f"ran {name}"


class BigToolset(FakeToolset):
    async def call_tool(self, name, tool_args, ctx, tool):
        return "x" * 1_000


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


@pytest.mark.asyncio
async def test_an_oversized_result_is_truncated_with_a_note(monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "tool_result_max_bytes", 100)
    result = await ToolBudgetToolset(wrapped=BigToolset(), budget=5).call_tool("mpmb_read", {}, None, None)
    assert result.startswith("x" * 100 + "\n[truncated: showing the first 100 of 1000 bytes")


def test_truncation_never_splits_a_multibyte_character():
    result = cap_result("\u00e9" * 100, 51)
    assert result.startswith("\u00e9" * 25 + "\n[truncated:")


def test_results_under_the_cap_and_non_text_results_pass_through():
    assert cap_result("short", 100) == "short"
    assert cap_result({"k": "v"}, 1) == {"k": "v"}
    assert cap_result("x" * 10, 0) == "x" * 10
