"""Tests for Planner."""
from __future__ import annotations

import functools
import inspect

import pytest

from effero.core.memory.working import WorkingMemory
from effero.core.planner.planner import Planner
from effero.core.router.base import LLMRequest, LLMResponse, ToolCall
from effero.sdk.skill import SafetyClass, SkillRegistry, SkillSpec


class MockRouter:
    """Mock model router that returns controlled responses."""

    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(responses)
        self._call_idx = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if self._call_idx < len(self.responses):
            resp = self.responses[self._call_idx]
            self._call_idx += 1
            return resp
        return LLMResponse(content="(exhausted)")


def _make_registry_with_skill() -> SkillRegistry:
    """Create a registry with a simple test skill."""
    reg = SkillRegistry()

    def add_fn(a: int, b: int) -> int:
        return a + b

    spec = SkillSpec(
        name="test.add",
        description="Add two numbers",
        safety_class=SafetyClass.READ_ONLY,
        func=add_fn,
        signature=inspect.signature(add_fn),
    )
    functools.update_wrapper(spec, add_fn)
    reg.register(spec)
    return reg


@pytest.mark.asyncio
async def test_simple_text_response() -> None:
    """LLM responds with text, no tool calls — planner returns it."""
    router = MockRouter([LLMResponse(content="Hello! How can I help?")])
    memory = WorkingMemory()
    skills = SkillRegistry()

    planner = Planner(router=router, memory=memory, skills=skills)
    result = await planner.run("hi")
    assert result == "Hello! How can I help?"


@pytest.mark.asyncio
async def test_tool_call_and_result() -> None:
    """LLM calls a tool, planner executes it, then LLM gives final answer."""
    router = MockRouter([
        # First response: call the test.add tool
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="call-1", name="test.add", arguments={"a": 2, "b": 3})],
        ),
        # Second response: text with the result
        LLMResponse(content="The result is 5."),
    ])
    memory = WorkingMemory()
    skills = _make_registry_with_skill()

    planner = Planner(router=router, memory=memory, skills=skills)
    result = await planner.run("What is 2 + 3?")
    assert "5" in result


@pytest.mark.asyncio
async def test_unknown_skill() -> None:
    """LLM calls a skill that doesn't exist — planner returns error."""
    router = MockRouter([
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="call-1", name="nonexistent.skill", arguments={})],
        ),
        LLMResponse(content="Sorry, that didn't work."),
    ])
    memory = WorkingMemory()
    skills = SkillRegistry()

    planner = Planner(router=router, memory=memory, skills=skills)
    result = await planner.run("do something")
    # Should eventually get a response (after the error is recorded)
    assert result is not None


@pytest.mark.asyncio
async def test_max_iterations() -> None:
    """Planner should stop after max_iterations."""
    # Router always returns tool calls, never text
    responses = [
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id=f"call-{i}", name="test.add", arguments={"a": 1, "b": 1})],
        )
        for i in range(20)
    ]
    router = MockRouter(responses)
    memory = WorkingMemory()
    skills = _make_registry_with_skill()

    planner = Planner(router=router, memory=memory, skills=skills, max_iterations=3)
    result = await planner.run("loop forever")
    assert result == "(max planning iterations reached)"
