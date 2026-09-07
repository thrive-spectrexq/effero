"""Agent-to-Agent protocol stub."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentCard:
    name: str
    description: str
    skills: list[str] = field(default_factory=list)
    endpoint: str = ""


class A2AClient:
    """Minimal stub for Agent-to-Agent protocol.
    
    Full implementation is planned for v0.3.
    """

    async def discover_agents(self) -> list[AgentCard]:
        logger.warning("A2A discover_agents is a stub.")
        return []

    async def send_task(self, agent_id: str, task: str) -> dict[str, Any]:
        logger.warning("A2A send_task is a stub.")
        return {"status": "mocked", "task_id": "mock-123"}

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        logger.warning("A2A get_task_status is a stub.")
        return {"status": "mocked", "completed": False}
