"""Fleet Coordinator for multi-agent negotiation, discovery, and distributed task routing."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from effero.core.event_bus import Event, EventBus
from effero.core.fleet.auction import (
    Bid,
    BidScorer,
    FailoverManager,
    LeaseManager,
    NodeModality,
    SealedBidAuction,
    TaskAnnouncement,
    TaskAward,
)
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
    modality: NodeModality = NodeModality.CLOUD_REASONING


class FleetCoordinator:
    """Coordinates a fleet of specialized physical and digital agents using A2A and Contract Net Protocol."""

    def __init__(
        self,
        client: A2AClient | None = None,
        scorer: BidScorer | None = None,
        default_lease_duration: float = 30.0,
        event_bus: EventBus | None = None,
    ) -> None:
        self.client = client or A2AClient()
        self.nodes: dict[str, FleetNode] = {}
        self.shared_state: dict[str, Any] = {}
        self.scorer = scorer or BidScorer()
        self.default_lease_duration = default_lease_duration
        self.event_bus = event_bus
        self.auction_engine = SealedBidAuction(scorer=self.scorer, default_lease_duration=self.default_lease_duration)
        self.lease_manager = LeaseManager(default_duration=self.default_lease_duration)
        self.failover_manager = FailoverManager(
            lease_manager=self.lease_manager,
            auction_engine=self.auction_engine,
        )

    def register_node(
        self,
        card: AgentCard,
        modality: NodeModality | str | None = None,
    ) -> FleetNode:
        """Register or update a node in the fleet registry with modality classification."""
        resolved_modality = NodeModality.from_str(modality)
        if resolved_modality is None:
            # Infer modality profile from skills and description
            all_text = " ".join(card.skills + [card.description or ""]).lower()
            if any(k in all_text for k in ["robotics", "navigate", "arm", "rover", "gripper"]):
                resolved_modality = NodeModality.ROBOTICS
            elif any(k in all_text for k in ["vision", "detect", "camera", "segment"]):
                resolved_modality = NodeModality.VISION_COMPUTE
            elif any(k in all_text for k in ["iot", "mqtt", "matter", "sensor", "gpio"]):
                resolved_modality = NodeModality.IOT_EDGE
            elif any(k in all_text for k in ["desktop", "browser", "win32", "keyboard", "mouse", "window"]):
                resolved_modality = NodeModality.DESKTOP_AUTOMATION
            else:
                resolved_modality = NodeModality.CLOUD_REASONING

        node = FleetNode(id=card.name, card=card, modality=resolved_modality)
        self.nodes[card.name] = node
        logger.info(f"Fleet registered agent: {card.name} ({card.endpoint}) [modality={resolved_modality.value}]")
        return node

    def unregister_node(self, node_id: str) -> bool:
        """Remove a node from the fleet."""
        # Clean up any active leases
        for lease in self.lease_manager.get_node_leases(node_id):
            self.lease_manager.revoke_lease(lease.task_id)
        return bool(self.nodes.pop(node_id, None))

    def announce_task(
        self,
        cfp_or_instruction: TaskAnnouncement | str | None = None,
        *,
        instruction: str = "",
        required_skills: list[str] | None = None,
        required_modality: NodeModality | str | None = None,
        deadline: float = 0.0,
        budget: float | None = None,
        auction_window: float = 5.0,
        sealed: bool = True,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Publish a task announcement / Call for Proposals (CFP) under Contract Net Protocol."""
        if isinstance(cfp_or_instruction, TaskAnnouncement):
            cfp = cfp_or_instruction
        elif "cfp" in kwargs and isinstance(kwargs["cfp"], TaskAnnouncement):
            cfp = kwargs["cfp"]
        else:
            instr = cfp_or_instruction if isinstance(cfp_or_instruction, str) else instruction
            tid = task_id or f"task-{uuid.uuid4().hex[:8]}"
            cfp = TaskAnnouncement(
                task_id=tid,
                instruction=instr,
                required_skills=required_skills or [],
                required_modality=required_modality,
                deadline=deadline,
                budget=budget,
                auction_window=auction_window,
                sealed=sealed,
                metadata=metadata or {},
            )
        tid = self.auction_engine.create_auction(cfp)
        if self.event_bus:
            self.event_bus.publish(
                Event(
                    topic="fleet.cfp.announced",
                    data={"task_id": tid, "cfp": asdict(cfp)},
                    source="fleet-coordinator",
                )
            )
        return tid

    def submit_bid(self, bid: Bid, current_time: float | None = None) -> bool:
        """Submit a node proposal / bid to an open task auction."""
        return self.auction_engine.submit_bid(bid, current_time=current_time)

    def evaluate_and_award(
        self,
        task_id: str,
        lease_duration: float | None = None,
        current_time: float | None = None,
    ) -> TaskAward | None:
        """Close auction, evaluate bids with multi-factor scoring, issue award and grant lease."""
        node_skills_map = {n.id: n.card.skills for n in self.nodes.values() if n.healthy}
        active_tasks_map = {n.id: n.active_tasks for n in self.nodes.values() if n.healthy}
        node_modality_map = {n.id: n.modality for n in self.nodes.values() if n.healthy}

        ttl = lease_duration or self.default_lease_duration
        award, _ = self.auction_engine.close_auction(
            task_id=task_id,
            node_skills_map=node_skills_map,
            active_tasks_map=active_tasks_map,
            node_modality_map=node_modality_map,
            lease_duration=ttl,
            current_time=current_time,
        )

        if award:
            self.lease_manager.create_lease(
                task_id=award.task_id,
                node_id=award.winning_node_id,
                duration=award.lease_duration,
                granted_at=award.awarded_at,
                lease_id=award.lease_id,
            )
            if award.winning_node_id in self.nodes:
                self.nodes[award.winning_node_id].active_tasks += 1

        return award

    def renew_lease(
        self,
        task_id: str,
        node_id: str,
        extension: float | None = None,
        current_time: float | None = None,
    ) -> bool:
        """Renew active task lease heartbeat for a node."""
        now = time.time() if current_time is None else current_time
        if node_id in self.nodes:
            self.nodes[node_id].last_heartbeat = now
        return self.lease_manager.renew_lease(
            task_id=task_id,
            node_id=node_id,
            extension=extension,
            current_time=current_time,
        )

    def check_leases_and_failover(self, current_time: float | None = None) -> list[str]:
        """Sweep expired leases, mark delinquent nodes unhealthy, and promote runner-up bids."""
        return self.failover_manager.process_expired_leases(self, current_time=current_time)

    def select_best_node(
        self,
        required_skills: list[str],
        required_modality: NodeModality | str | None = None,
    ) -> FleetNode | None:
        """Contract-net capability matching to find the best suited agent node."""
        candidates = [n for n in self.nodes.values() if n.healthy]
        if not candidates:
            return None

        target_modality = NodeModality.from_str(required_modality)

        def score_node(n: FleetNode) -> float:
            matching_skills = sum(1 for s in required_skills if s in n.card.skills)
            modality_bonus = 5.0 if (target_modality and n.modality == target_modality) else 0.0
            # Higher score for matching skills and modality, lower for current workload
            return (matching_skills * 10.0) + modality_bonus - (n.active_tasks * 2.0)

        best = max(candidates, key=score_node)
        return best

    async def delegate(
        self,
        instruction: str,
        required_skills: list[str] | None = None,
        context: dict[str, Any] | None = None,
        required_modality: NodeModality | str | None = None,
    ) -> TaskMessage:
        """Delegate task to the optimal fleet agent."""
        node = self.select_best_node(required_skills or [], required_modality=required_modality)
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
        """Store a shared fact in the fleet coordinator's local state dictionary."""
        self.shared_state[key] = value

    def get_shared_fact(self, key: str, default: Any = None) -> Any:
        return self.shared_state.get(key, default)
