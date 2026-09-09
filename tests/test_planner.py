"""Tests for Planner."""

from __future__ import annotations

import functools
import inspect

import pytest

from effero.core.memory.working import WorkingMemory
from effero.core.planner.planner import Planner
from effero.core.router import ScriptedBackend
from effero.core.router.base import LLMResponse, ToolCall
from effero.sdk.skill import SafetyClass, SkillRegistry, SkillSpec


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
    router = ScriptedBackend([LLMResponse(content="Hello! How can I help?")])
    memory = WorkingMemory()
    skills = SkillRegistry()

    planner = Planner(router=router, memory=memory, skills=skills)
    result = await planner.run("hi")
    assert result == "Hello! How can I help?"


@pytest.mark.asyncio
async def test_tool_call_and_result() -> None:
    """LLM calls a tool, planner executes it, then LLM gives final answer."""
    router = ScriptedBackend(
        [
            # First response: call the test.add tool
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="call-1", name="test.add", arguments={"a": 2, "b": 3})],
            ),
            # Second response: text with the result
            LLMResponse(content="The result is 5."),
        ]
    )
    memory = WorkingMemory()
    skills = _make_registry_with_skill()

    planner = Planner(router=router, memory=memory, skills=skills)
    result = await planner.run("What is 2 + 3?")
    assert "5" in result


@pytest.mark.asyncio
async def test_unknown_skill() -> None:
    """LLM calls a skill that doesn't exist — planner returns error."""
    router = ScriptedBackend(
        [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="call-1", name="nonexistent.skill", arguments={})],
            ),
            LLMResponse(content="Sorry, that didn't work."),
        ]
    )
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
    router = ScriptedBackend(responses)
    memory = WorkingMemory()
    skills = _make_registry_with_skill()

    planner = Planner(router=router, memory=memory, skills=skills, max_iterations=3)
    result = await planner.run("loop forever")
    assert result == "(max planning iterations reached)"


class _FakeSafetyClient:
    def __init__(self, decision: str = "allow", reason: str = "", limit: dict[str, float] | None = None):
        self.connected = True
        self.decision = decision
        self.reason = reason
        self.limit = limit
        self.recorded_calls: list[tuple[str, dict]] = []

    async def check_action(self, skill_name: str, facts: dict | None = None) -> dict:
        self.recorded_calls.append((skill_name, facts or {}))
        resp = {"decision": self.decision, "reason": self.reason}
        if self.limit is not None:
            resp["limit"] = self.limit
        return resp


@pytest.mark.asyncio
async def test_safety_kernel_facts_wiring() -> None:
    """Verify that skill arguments, environment facts, telemetry, and facts_provider are sent to safety client."""
    fake_safety = _FakeSafetyClient(decision="allow")
    memory = WorkingMemory()
    memory.record_metric("nearest_person_distance_m", 0.45)
    memory.record_metric("battery_pct", 88.0)

    skills = _make_registry_with_skill()
    router = ScriptedBackend(
        [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="call-1", name="test.add", arguments={"a": 10, "b": 20})],
            ),
            LLMResponse(content="Done"),
        ]
    )

    def custom_facts(name, args):
        return {"external_sensor_reading": 12.5, "alarm_active": False}

    planner = Planner(
        router=router,
        memory=memory,
        skills=skills,
        safety_client=fake_safety,  # type: ignore[arg-type]
        facts_provider=custom_facts,
    )
    result = await planner.run("Add 10 and 20")
    assert result == "Done"

    assert len(fake_safety.recorded_calls) == 1
    skill_name, facts = fake_safety.recorded_calls[0]
    assert skill_name == "test.add"

    # 1. Skill arguments in facts
    assert facts["a"] == 10.0
    assert facts["b"] == 20.0
    assert facts["arg_a"] == 10.0

    # 2. Environment/time facts
    assert "time_hour" in facts
    assert "time_minute" in facts
    assert isinstance(facts["time_hour"], float)
    assert isinstance(facts["is_night"], bool)

    # 3. WorkingMemory telemetry facts
    assert facts["nearest_person_distance_m"] == 0.45
    assert facts["battery_pct"] == 88.0

    # 4. Custom facts provider
    assert facts["external_sensor_reading"] == 12.5
    assert facts["alarm_active"] is False


@pytest.mark.asyncio
async def test_safety_kernel_deny_decision() -> None:
    """Verify safety client deny decision halts execution and returns error."""
    fake_safety = _FakeSafetyClient(decision="deny", reason="Proximity violation: person within 0.5m")
    memory = WorkingMemory()
    skills = _make_registry_with_skill()
    router = ScriptedBackend(
        [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="call-1", name="test.add", arguments={"a": 1, "b": 2})],
            ),
            LLMResponse(content="I could not execute the action."),
        ]
    )

    planner = Planner(router=router, memory=memory, skills=skills, safety_client=fake_safety)  # type: ignore[arg-type]
    result = await planner.run("Execute addition")
    assert result is not None

    tool_msgs = [m for m in memory.get_context() if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert "Safety policy denied: Proximity violation" in str(tool_msgs[0].get("content"))


@pytest.mark.asyncio
async def test_safety_kernel_limit_clamping() -> None:
    """Verify safety limit decision clamps excessive argument values down to maximum safe limit."""
    fake_safety = _FakeSafetyClient(
        decision="limit",
        reason="Human within 1m: speed clamped to 0.5 m/s",
        limit={"max_speed": 0.5},
    )
    memory = WorkingMemory()

    def navigate_fn(speed: float) -> str:
        return f"Moving at speed {speed}"

    spec = SkillSpec(
        name="robotics.navigate",
        description="Navigate robot",
        safety_class=SafetyClass.ACT_AUTONOMOUS,
        func=navigate_fn,
        signature=inspect.signature(navigate_fn),
    )
    functools.update_wrapper(spec, navigate_fn)
    skills = SkillRegistry()
    skills.register(spec)

    router = ScriptedBackend(
        [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="call-1", name="robotics.navigate", arguments={"speed": 2.5})],
            ),
            LLMResponse(content="Action executed at reduced speed."),
        ]
    )

    planner = Planner(router=router, memory=memory, skills=skills, safety_client=fake_safety)  # type: ignore[arg-type]
    result = await planner.run("Drive forward at 2.5 m/s")
    assert result == "Action executed at reduced speed."

    tool_msgs = [m for m in memory.get_context() if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    # Check that the tool result was indeed clamped to 0.5
    assert "Moving at speed 0.5" in str(tool_msgs[0].get("content"))

    # Also verify the safety clamping event was recorded in memory
    memory_thoughts = [
        m.get("content")
        for m in memory.get_context()
        if "Clamped 'robotics.navigate' argument 'speed' from 2.5 to 0.5" in str(m.get("content"))
    ]
    assert len(memory_thoughts) == 1
