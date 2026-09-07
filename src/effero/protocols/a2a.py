"""Agent-to-Agent (A2A) protocol implementation for multi-agent delegation and discovery."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TaskState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentCard:
    """Public discovery metadata card for an Effero agent node."""

    name: str
    description: str
    endpoint: str
    version: str = "0.2.0"
    skills: list[str] = field(default_factory=list)
    modalities: list[str] = field(default_factory=lambda: ["text", "voice", "vision", "robotics", "iot"])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentCard:
        return cls(
            name=data["name"],
            description=data["description"],
            endpoint=data["endpoint"],
            version=data.get("version", "0.2.0"),
            skills=data.get("skills", []),
            modalities=data.get("modalities", []),
        )


@dataclass
class TaskMessage:
    """A task delegating an instruction to a peer agent."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = "effero-primary"
    instruction: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    state: TaskState = TaskState.PENDING
    result: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskMessage:
        return cls(
            task_id=data["task_id"],
            sender=data.get("sender", "unknown"),
            instruction=data.get("instruction", ""),
            context=data.get("context", {}),
            state=TaskState(data.get("state", "pending")),
            result=data.get("result"),
            error=data.get("error"),
            created_at=data.get("created_at", time.time()),
            completed_at=data.get("completed_at"),
        )


class A2AClient:
    """HTTP client communicating with peer Effero agents over the A2A protocol."""

    def __init__(self, timeout_seconds: float = 30.0):
        self.timeout_seconds = timeout_seconds

    async def fetch_agent_card(self, endpoint: str) -> AgentCard:
        """Query a remote agent's discovery card."""
        url = endpoint.rstrip("/") + "/v1/agent-card"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return AgentCard.from_dict(resp.json())

    async def delegate_task(
        self,
        endpoint: str,
        instruction: str,
        context: dict[str, Any] | None = None,
        sender_id: str = "effero-agent",
    ) -> TaskMessage:
        """Send a task to a peer agent and wait for initial acknowledgement or result."""
        url = endpoint.rstrip("/") + "/v1/tasks"
        payload = {
            "sender": sender_id,
            "instruction": instruction,
            "context": context or {},
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return TaskMessage.from_dict(resp.json())

    async def get_task_status(self, endpoint: str, task_id: str) -> TaskMessage:
        """Poll execution status of a delegated task."""
        url = endpoint.rstrip("/") + f"/v1/tasks/{task_id}"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return TaskMessage.from_dict(resp.json())

    async def discover_peers(self, registry_url: str) -> list[AgentCard]:
        """Discover peer agents from an A2A directory or local mesh."""
        url = registry_url.rstrip("/") + "/v1/peers"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                return [AgentCard.from_dict(item) for item in data.get("peers", [])]
        except Exception as e:
            logger.warning(f"Could not discover peers from {registry_url}: {e}")
            return []


class A2ATaskManager:
    """Local manager storing and dispatching tasks received from peer agents."""

    def __init__(self, agent_instance=None):
        self.agent = agent_instance
        self.tasks: dict[str, TaskMessage] = {}

    def create_task(self, sender: str, instruction: str, context: dict[str, Any]) -> TaskMessage:
        task = TaskMessage(
            sender=sender,
            instruction=instruction,
            context=context,
            state=TaskState.PENDING,
        )
        self.tasks[task.task_id] = task
        return task

    async def execute_task(self, task_id: str) -> TaskMessage:
        if task_id not in self.tasks:
            raise KeyError(f"Task {task_id} not found")

        task = self.tasks[task_id]
        task.state = TaskState.RUNNING

        try:
            if self.agent:
                result = await self.agent.run(task.instruction)
            else:
                result = f"Processed instruction: {task.instruction}"

            task.result = str(result)
            task.state = TaskState.COMPLETED
        except Exception as e:
            task.error = str(e)
            task.state = TaskState.FAILED
        finally:
            task.completed_at = time.time()

        return task

    def get_task(self, task_id: str) -> TaskMessage | None:
        return self.tasks.get(task_id)
