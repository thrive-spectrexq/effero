"""Fleet Coordinator for multi-agent negotiation, discovery, and distributed task routing."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from effero.protocols.a2a import A2AClient, AgentCard, TaskMessage

logger = logging.getLogger(__name__)


@dataclass
class FleetNode:
    """A registered agent node in the multi-agent fleet."""

    id: str
    card: AgentCard
    last_heartbeat: float = field(default_factory=time.time)
    active_tasks: int = 0
    healthy: bool = True


class FleetCoordinator:
    """Coordinates a fleet of specialized physical and digital agents using A2A protocol."""

    def __init__(self, client: A2AClient | None = None):
        self.client = client or A2AClient()
        self.nodes: dict[str, FleetNode] = {}
        self.shared_state: dict[str, Any] = {}

    def register_node(self, card: AgentCard) -> FleetNode:
        """Register or update a node in the fleet registry."""
        node = FleetNode(id=card.name, card=card)
        self.nodes[card.name] = node
        logger.info(f"Fleet registered agent: {card.name} ({card.endpoint})")
        return node

    def unregister_node(self, node_id: str) -> bool:
        """Remove a node from the fleet."""
        return bool(self.nodes.pop(node_id, None))

    def select_best_node(self, required_skills: list[str]) -> FleetNode | None:
        """Contract-net capability matching to find the best suited agent node."""
        candidates = [n for n in self.nodes.values() if n.healthy]
        if not candidates:
            return None

        def score_node(n: FleetNode) -> float:
            matching_skills = sum(1 for s in required_skills if s in n.card.skills)
            # Higher score for matching skills, lower for current workload
            return (matching_skills * 10.0) - (n.active_tasks * 2.0)

        best = max(candidates, key=score_node)
        return best

    async def delegate(
        self,
        instruction: str,
        required_skills: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> TaskMessage:
        """Delegate task to the optimal fleet agent."""
        node = self.select_best_node(required_skills or [])
        if not node:
            raise RuntimeError("No suitable fleet node available to handle delegation")

        node.active_tasks += 1
        merged_context = dict(self.shared_state)
        if context:
            merged_context.update(context)

        try:
            logger.info(f"Delegating '{instruction}' to node {node.id}")
            task = await self.client.delegate_task(
                endpoint=node.card.endpoint,
                instruction=instruction,
                context=merged_context,
            )
            return task
        finally:
            node.active_tasks = max(0, node.active_tasks - 1)

    def set_shared_fact(self, key: str, value: Any) -> None:
        """Broadcast / update a shared distributed memory fact across the fleet."""
        self.shared_state[key] = value

    def get_shared_fact(self, key: str, default: Any = None) -> Any:
        return self.shared_state.get(key, default)
