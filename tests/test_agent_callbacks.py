"""Tests for Agent lifecycle callbacks and telemetry."""

from __future__ import annotations

import functools
import inspect
from typing import Any

import pytest

from effero.core.agent import Agent
from effero.core.callbacks.base import AgentCallback, CallbackList
from effero.core.callbacks.telemetry import AuditLogCallback, TelemetryCallback
from effero.core.memory.working import WorkingMemory
from effero.core.planner.planner import Planner
from effero.core.router import ScriptedBackend
from effero.core.router.base import LLMResponse, ToolCall
from effero.sdk.skill import SafetyClass, SkillRegistry, SkillSpec


class TrackingCallback(AgentCallback):
    def __init__(self) -> None:
        self.events: list[str] = []

    def on_agent_start(self, prompt: str) -> None:
        self.events.append(f"start:{prompt}")

    def on_agent_finish(self, response: str, elapsed_seconds: float) -> None:
        self.events.append(f"finish:{response}")

    def on_agent_error(self, error: Exception) -> None:
        self.events.append(f"error:{error}")

    def on_plan_generated(self, plan: Any) -> None:
        self.events.append("plan_generated")

    def on_skill_before_execute(self, skill_name: str, arguments: dict[str, Any]) -> None:
        self.events.append(f"before:{skill_name}")

    def on_skill_after_execute(self, skill_name: str, result: Any, elapsed_seconds: float) -> None:
        self.events.append(f"after:{skill_name}:{result}")

    def on_safety_check(
        self, skill_name: str, arguments: dict[str, Any], approved: bool, reason: str | None = None
    ) -> None:
        self.events.append(f"safety:{skill_name}:{approved}")


class CrashingCallback(AgentCallback):
    def on_agent_start(self, prompt: str) -> None:
        raise RuntimeError("Callback crash simulation")

    def on_skill_before_execute(self, skill_name: str, arguments: dict[str, Any]) -> None:
        raise RuntimeError("Callback crash in skill hook")


def _build_test_registry() -> SkillRegistry:
    reg = SkillRegistry()

    def multiply(a: int, b: int) -> int:
        return a * b

    spec = SkillSpec(
        name="math.multiply",
        description="Multiply numbers",
        safety_class=SafetyClass.READ_ONLY,
        func=multiply,
        signature=inspect.signature(multiply),
    )
    functools.update_wrapper(spec, multiply)
    reg.register(spec)
    return reg


@pytest.mark.asyncio
async def test_planner_callback_lifecycle():
    tracker = TrackingCallback()
    callbacks = CallbackList([tracker])
    skills = _build_test_registry()
    memory = WorkingMemory()

    router = ScriptedBackend(
        [
            LLMResponse(
                content="Multiplying",
                tool_calls=[ToolCall(id="c1", name="math.multiply", arguments={"a": 3, "b": 7})],
            ),
            LLMResponse(content="The answer is 21"),
        ]
    )

    planner = Planner(
        router=router,
        memory=memory,
        skills=skills,
        callbacks=callbacks,
    )

    result = await planner.run("Multiply 3 by 7")
    assert result == "The answer is 21"

    # Verify event sequencing
    assert "plan_generated" in tracker.events
    assert "safety:math.multiply:True" in tracker.events
    assert "before:math.multiply" in tracker.events
    assert "after:math.multiply:21" in tracker.events


@pytest.mark.asyncio
async def test_callback_list_exception_isolation():
    tracker = TrackingCallback()
    crashing = CrashingCallback()
    cblist = CallbackList([crashing, tracker])

    # Should not raise exception even though crashing callback throws
    cblist.on_agent_start("test prompt")
    cblist.on_skill_before_execute("any_skill", {})

    assert "start:test prompt" in tracker.events
    assert "before:any_skill" in tracker.events


@pytest.mark.asyncio
async def test_telemetry_and_audit_callbacks():
    memory = WorkingMemory()
    telemetry = TelemetryCallback(memory=memory)
    audit = AuditLogCallback(log_to_logger=False)
    callbacks = CallbackList([telemetry, audit])

    skills = _build_test_registry()
    router = ScriptedBackend(
        [
            LLMResponse(
                content="Calling multiply",
                tool_calls=[ToolCall(id="c2", name="math.multiply", arguments={"a": 2, "b": 5})],
            ),
            LLMResponse(content="Result is 10"),
        ]
    )

    planner = Planner(
        router=router,
        memory=memory,
        skills=skills,
        callbacks=callbacks,
    )

    agent = Agent(
        skills=skills,
        callbacks=callbacks,
    )
    # inject mock planner
    agent.planner = planner

    output = await agent.run("Calculate 2 * 5")
    assert output == "Result is 10"

    summary = telemetry.get_summary()
    assert summary["total_agent_runs"] == 1
    assert summary["total_skill_invocations"] == 1
    assert summary["skill_counts"]["math.multiply"] == 1
    assert summary["safety_decisions"]["approved"] == 1
    assert summary["average_agent_latency_s"] > 0.0

    # Verify audit records
    event_types = [r["event_type"] for r in audit.audit_records]
    assert "agent_start" in event_types
    assert "plan_generated" in event_types
    assert "safety_check" in event_types
    assert "skill_call" in event_types
    assert "skill_result" in event_types
    assert "agent_finish" in event_types

    # Verify working memory recorded telemetry streams
    assert memory.get_latest_metric("agent_runs") == 1
    assert memory.get_latest_metric("skill_calls_math.multiply") == 1
