"""Benchmark for Agent Planner loop and tool execution."""

from __future__ import annotations

import asyncio
import functools
import inspect
from typing import Any

from effero.core.memory.working import WorkingMemory
from effero.core.planner.planner import Planner
from effero.core.router import ScriptedBackend
from effero.core.router.base import LLMResponse, ToolCall
from effero.sdk.skill import SafetyClass, SkillRegistry, SkillSpec


def _make_benchmark_planner() -> Planner:
    reg = SkillRegistry()

    def add_fn(a: int, b: int) -> int:
        return a + b

    spec = SkillSpec(
        name="math.add",
        description="Add two numbers",
        safety_class=SafetyClass.READ_ONLY,
        func=add_fn,
        signature=inspect.signature(add_fn),
    )
    functools.update_wrapper(spec, add_fn)
    reg.register(spec)

    responses = [
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="call-bench", name="math.add", arguments={"a": 10, "b": 25})],
        ),
        LLMResponse(content="The sum is 35."),
    ]
    router = ScriptedBackend(responses)
    memory = WorkingMemory()
    return Planner(router=router, memory=memory, skills=reg)


def test_bench_planner_tool_cycle(benchmark: Any) -> None:
    """Benchmark full Planner step: user prompt -> LLM tool call -> skill execution -> LLM summary."""

    def run_cycle() -> str:
        planner = _make_benchmark_planner()
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(planner.run("calculate 10 + 25"))
        finally:
            loop.close()

    res = benchmark(run_cycle)
    assert res == "The sum is 35."
