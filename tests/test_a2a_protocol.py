"""Tests for A2A protocol models and real A2ATaskManager execution lifecycle."""

from __future__ import annotations

import pytest

from effero.config import EfferoConfig
from effero.core.agent import Agent
from effero.protocols.a2a import (
    A2ATaskManager,
    AgentCard,
    TaskMessage,
    TaskState,
)


def test_agent_card_roundtrip() -> None:
    card = AgentCard(
        name="edge-node-01",
        description="Raspberry Pi Edge Controller",
        endpoint="http://192.168.1.50:8000",
        version="0.2.0",
        skills=["iot.gpio.read", "iot.gpio.write"],
        modalities=["iot", "sensors"],
    )
    d = card.to_dict()
    restored = AgentCard.from_dict(d)

    assert restored.name == card.name
    assert restored.endpoint == card.endpoint
    assert restored.skills == ["iot.gpio.read", "iot.gpio.write"]
    assert restored.modalities == ["iot", "sensors"]


def test_task_message_lifecycle_states() -> None:
    task = TaskMessage(
        sender="planner-01",
        instruction="Check battery level",
        context={"priority": "high"},
    )
    assert task.state == TaskState.PENDING
    assert task.result is None
    assert task.error is None
    assert task.completed_at is None

    d = task.to_dict()
    assert d["state"] == "pending"
    assert d["sender"] == "planner-01"

    restored = TaskMessage.from_dict(d)
    assert restored.task_id == task.task_id
    assert restored.state == TaskState.PENDING


@pytest.mark.asyncio
async def test_a2a_task_manager_standalone_execution() -> None:
    # A2ATaskManager with no attached agent executes standalone instructions
    manager = A2ATaskManager(agent_instance=None)
    task = manager.create_task(
        sender="coordinator",
        instruction="Turn on work lights",
        context={"room": "lab"},
    )
    assert manager.get_task(task.task_id) is task
    assert task.state == TaskState.PENDING

    completed_task = await manager.execute_task(task.task_id)
    assert completed_task.state == TaskState.COMPLETED
    assert completed_task.result == "Processed instruction: Turn on work lights"
    assert completed_task.completed_at is not None
    assert completed_task.error is None


@pytest.mark.asyncio
async def test_a2a_task_manager_with_real_agent_instance() -> None:
    # Use the real production Agent class
    config = EfferoConfig()
    real_agent = Agent(config=config)
    manager = A2ATaskManager(agent_instance=real_agent)

    task = manager.create_task(
        sender="coordinator",
        instruction="Ping telemetry",
        context={},
    )
    # The real agent attempts to run with unconfigured API keys, resulting in a real backend error
    completed_task = await manager.execute_task(task.task_id)
    assert completed_task.state == TaskState.FAILED
    assert completed_task.completed_at is not None
    assert (
        "LLM" in (completed_task.error or "")
        or "API" in (completed_task.error or "")
        or len(completed_task.error or "") > 0
    )


@pytest.mark.asyncio
async def test_a2a_task_manager_missing_task_raises() -> None:
    manager = A2ATaskManager()
    with pytest.raises(KeyError, match="Task nonexistent-id not found"):
        await manager.execute_task("nonexistent-id")
