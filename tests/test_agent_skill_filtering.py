"""Tests for Agent skill filtering and wildcard require_approval_for matching."""

from __future__ import annotations

import pytest

from effero.config import AgentConfig, EfferoConfig, ModelConfig, SafetyConfig
from effero.core.agent import Agent
from effero.core.router import ScriptedBackend
from effero.core.router.base import LLMResponse, ToolCall
from effero.safety.approval import AutoApprovalHandler


@pytest.mark.asyncio
async def test_agent_skill_filtering() -> None:
    """Verify Agent filters global skill registry down to matching config patterns."""
    config = EfferoConfig(
        agent=AgentConfig(
            name="filtered-agent",
            model=ModelConfig(backend="openai", model="test"),
        ),
        skills=["iot.lights.*", "computer_use.file.read"],
    )

    agent = Agent(config)
    await agent.start()

    available = agent.available_skills()
    assert "computer_use.file.read" in available
    assert any(s.startswith("iot.lights.") for s in available)
    # Excluded skills should not be in available
    assert "computer_use.shell.run" not in available
    assert "robotics.navigate.go_to" not in available

    await agent.stop()


@pytest.mark.asyncio
async def test_require_approval_for_wildcard_matching() -> None:
    """Verify Planner flags skills matching require_approval_for wildcard patterns."""
    config = EfferoConfig(
        agent=AgentConfig(
            name="safety-agent",
            model=ModelConfig(backend="openai", model="test"),
        ),
        safety=SafetyConfig(
            enabled=True,
            require_approval_for=["robotics.arm.home"],  # Normally ACT_AUTONOMOUS
        ),
    )

    approval_handler = AutoApprovalHandler(approve_all=False)
    agent = Agent(config, approval_handler=approval_handler)
    await agent.start()

    # Script the router to request robotics.arm.home
    agent.router.backends = [
        ScriptedBackend(
            [
                LLMResponse(
                    content=None,
                    tool_calls=[ToolCall(id="c1", name="robotics.arm.home", arguments={})],
                ),
                LLMResponse(content="Action completed or handled."),
            ]
        )
    ]

    await agent.run("Home the robot arm")

    # The action was rejected by human operator handler because require_approval_for matched!
    assert len(approval_handler.history) == 1
    req, res = approval_handler.history[0]
    assert req.skill_name == "robotics.arm.home"
    assert res.approved is False

    await agent.stop()
