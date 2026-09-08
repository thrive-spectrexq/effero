"""Contract Net Protocol (CNP), Sealed-Bid Auction Engine, Leases, and Failover."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from effero.core.fleet.coordinator import FleetCoordinator

logger = logging.getLogger(__name__)


class NodeModality(StrEnum):
    """Specialized hardware modality profile for heterogeneous swarm nodes."""

    ROBOTICS = "robotics"
    VISION_COMPUTE = "vision_compute"
    IOT_EDGE = "iot_edge"
    DESKTOP_AUTOMATION = "desktop_automation"
    CLOUD_REASONING = "cloud_reasoning"

    @classmethod
    def from_str(cls, val: str | NodeModality | None) -> NodeModality | None:
        """Parse or normalize a modality string or enum."""
        if val is None:
            return None
        if isinstance(val, cls):
            return val
        s = str(val).lower().strip()
        for member in cls:
            if member.value == s:
                return member
        return None


@dataclass
class TaskAnnouncement:
    """Call for Proposals (CFP) / Task Announcement under Contract Net Protocol."""

    task_id: str
    instruction: str
    required_skills: list[str] = field(default_factory=list)
    required_modality: NodeModality | str | None = None
    deadline: float = 0.0
    budget: float | None = None
    auction_window: float = 5.0
    sealed: bool = True
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_window_open(self, current_time: float | None = None) -> bool:
        """Check if the auction bidding window is still open."""
        now = time.time() if current_time is None else current_time
        return now <= (self.created_at + self.auction_window)


# Alias CallForProposals to TaskAnnouncement for standard CNP nomenclature
CallForProposals = TaskAnnouncement


@dataclass
class Bid:
    """Node proposal submitted in response to a TaskAnnouncement."""

    bid_id: str
    task_id: str
    node_id: str
    cost: float = 0.0
    estimated_duration: float = 1.0
    capability_score: float = 1.0
    sealed: bool = False
    commitment_hash: str | None = None
    timestamp: float = field(default_factory=time.time)
    modality: NodeModality | str | None = None
    queue_depth: int = 0
    skills: list[str] = field(default_factory=list)
    salt: str | None = None
    unsealed_payload: dict[str, Any] | None = None

    def compute_commitment(self, salt: str) -> str:
        """Compute SHA-256 cryptographic commitment hash for sealed-bid commit-reveal."""
        payload = f"{self.task_id}:{self.node_id}:{self.cost:.6f}:{self.estimated_duration:.6f}:{self.capability_score:.6f}:{salt}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def verify_commitment(self, salt: str, commitment_hash: str | None = None) -> bool:
        """Verify that salt matches the commitment hash."""
        expected = commitment_hash or self.commitment_hash
        if not expected:
            return False
        computed = self.compute_commitment(salt)
        return hmac.compare_digest(computed, expected)


@dataclass
class TaskAward:
    """Contract award notice sent to the winning bidder."""

    task_id: str
    winning_node_id: str
    lease_id: str
    lease_duration: float
    awarded_at: float = field(default_factory=time.time)
    bid_id: str = ""
    score: float = 0.0


@dataclass
class BidRejection:
    """Notice sent to non-winning bidders explaining the rejection rationale."""

    task_id: str
    node_id: str
    reason: str
    bid_id: str = ""


@dataclass
class TaskLease:
    """Time-bounded lease granting a node execution rights for a delegated task."""

    lease_id: str
    task_id: str
    node_id: str
    granted_at: float = field(default_factory=time.time)
    duration: float = 30.0  # TTL in seconds
    last_heartbeat: float = field(default_factory=time.time)

    def is_expired(self, current_time: float | None = None) -> bool:
        """Check if lease duration has elapsed without heartbeat renewal."""
        now = time.time() if current_time is None else current_time
        return now > (self.last_heartbeat + self.duration)

    def renew(self, extension: float | None = None, current_time: float | None = None) -> None:
        """Renew the lease heartbeat and optionally adjust lease TTL."""
        now = time.time() if current_time is None else current_time
        self.last_heartbeat = now
        if extension is not None and extension > 0:
            self.duration = extension


class LeaseManager:
    """Tracks active task leases, validates heartbeats, and reaps expired leases."""

    def __init__(self, default_duration: float = 30.0) -> None:
        self.default_duration = default_duration
        self._leases: dict[str, TaskLease] = {}  # task_id -> TaskLease

    def create_lease(
        self,
        task_id: str,
        node_id: str,
        duration: float | None = None,
        granted_at: float | None = None,
        lease_id: str | None = None,
    ) -> TaskLease:
        """Issue a new task lease."""
        ttl = duration if duration is not None and duration > 0 else self.default_duration
        t_grant = time.time() if granted_at is None else granted_at
        lid = lease_id or f"lease-{uuid.uuid4().hex[:8]}"
        lease = TaskLease(
            lease_id=lid,
            task_id=task_id,
            node_id=node_id,
            granted_at=t_grant,
            duration=ttl,
            last_heartbeat=t_grant,
        )
        self._leases[task_id] = lease
        logger.info(f"Granted lease {lease.lease_id} for task {task_id} to node {node_id} (TTL={ttl}s)")
        return lease

    def renew_lease(
        self,
        task_id: str,
        node_id: str,
        extension: float | None = None,
        current_time: float | None = None,
    ) -> bool:
        """Renew a task lease heartbeat for the given node."""
        lease = self._leases.get(task_id)
        if not lease:
            logger.warning(f"Lease renewal failed: no active lease for task {task_id}")
            return False
        if lease.node_id != node_id:
            logger.warning(f"Lease renewal rejected: task {task_id} lease held by {lease.node_id}, not {node_id}")
            return False
        if lease.is_expired(current_time):
            logger.warning(f"Lease renewal rejected: lease {lease.lease_id} already expired")
            return False

        lease.renew(extension=extension, current_time=current_time)
        return True

    def get_lease(self, task_id: str) -> TaskLease | None:
        """Retrieve the active lease for a task."""
        return self._leases.get(task_id)

    def revoke_lease(self, task_id: str) -> TaskLease | None:
        """Revoke and remove a lease for a task."""
        return self._leases.pop(task_id, None)

    def check_expired_leases(self, current_time: float | None = None) -> list[TaskLease]:
        """Sweep and return all currently expired leases."""
        now = time.time() if current_time is None else current_time
        return [lease for lease in self._leases.values() if lease.is_expired(now)]

    def get_node_leases(self, node_id: str) -> list[TaskLease]:
        """Return all leases held by a specific node."""
        return [lease for lease in self._leases.values() if lease.node_id == node_id]

    @property
    def active_leases(self) -> dict[str, TaskLease]:
        """Return a copy of active leases mapping task_id to TaskLease."""
        return dict(self._leases)


class BidScorer:
    """Multi-factor bid scoring engine balancing skills, queue depth, duration, cost, and modalities."""

    def __init__(
        self,
        w_skill: float = 0.35,
        w_workload: float = 0.20,
        w_duration: float = 0.15,
        w_cost: float = 0.15,
        w_modality: float = 0.15,
        strict_modality: bool = False,
        strict_skills: bool = False,
    ) -> None:
        self.w_skill = w_skill
        self.w_workload = w_workload
        self.w_duration = w_duration
        self.w_cost = w_cost
        self.w_modality = w_modality
        self.strict_modality = strict_modality
        self.strict_skills = strict_skills

    def score_bid(
        self,
        cfp: TaskAnnouncement,
        bid: Bid,
        node_skills: list[str] | None = None,
        active_tasks: int | None = None,
        node_modality: str | NodeModality | None = None,
    ) -> float:
        """Evaluate a bid and return a normalized composite score in [0.0, 1.0]."""
        # 1. Skill Match Coverage
        available_skills = set(bid.skills)
        if node_skills:
            available_skills.update(node_skills)

        if not cfp.required_skills:
            skill_score = 1.0
        else:
            matching = sum(1 for s in cfp.required_skills if s in available_skills)
            skill_score = matching / len(cfp.required_skills)

        if self.strict_skills and skill_score < 1.0:
            return 0.0

        # Scale by node's self-reported capability score
        capability = max(0.0, min(1.0, bid.capability_score))
        skill_factor = skill_score * capability

        # 2. Node Workload / Queue Depth Penalty
        workload = bid.queue_depth if active_tasks is None else active_tasks
        workload_factor = 1.0 / (1.0 + max(0, workload))

        # 3. Latency / Estimated Duration Penalty
        duration = max(0.0, bid.estimated_duration)
        duration_factor = 1.0 / (1.0 + duration)

        # 4. Cost Factor
        cost = max(0.0, bid.cost)
        if cfp.budget is not None and cfp.budget > 0:
            if cost > cfp.budget:
                cost_factor = 0.0
            else:
                cost_factor = max(0.0, 1.0 - (cost / (cfp.budget * 1.2)))
        else:
            cost_factor = 1.0 / (1.0 + cost)

        # 5. Heterogeneous Modality Weight
        target_modality = NodeModality.from_str(cfp.required_modality)
        actual_modality = NodeModality.from_str(bid.modality) or NodeModality.from_str(node_modality)

        if target_modality is None:
            modality_factor = 1.0
        else:
            if actual_modality == target_modality:
                modality_factor = 1.0
            else:
                if self.strict_modality:
                    return 0.0
                modality_factor = 0.1  # Heavy penalty for modality mismatch

        total_weight = self.w_skill + self.w_workload + self.w_duration + self.w_cost + self.w_modality
        if total_weight <= 0:
            total_weight = 1.0

        composite = (
            self.w_skill * skill_factor
            + self.w_workload * workload_factor
            + self.w_duration * duration_factor
            + self.w_cost * cost_factor
            + self.w_modality * modality_factor
        ) / total_weight

        return round(max(0.0, min(1.0, composite)), 6)

    def rank_bids(
        self,
        cfp: TaskAnnouncement,
        bids: list[Bid],
        node_skills_map: Mapping[str, list[str]] | None = None,
        active_tasks_map: Mapping[str, int] | None = None,
        node_modality_map: Mapping[str, NodeModality | str] | None = None,
    ) -> list[tuple[Bid, float]]:
        """Score and sort bids in descending order."""
        scored: list[tuple[Bid, float]] = []
        for b in bids:
            n_skills = node_skills_map.get(b.node_id) if node_skills_map else None
            n_tasks = active_tasks_map.get(b.node_id) if active_tasks_map else None
            n_modality = node_modality_map.get(b.node_id) if node_modality_map else None

            score = self.score_bid(
                cfp=cfp,
                bid=b,
                node_skills=n_skills,
                active_tasks=n_tasks,
                node_modality=n_modality,
            )
            scored.append((b, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored


@dataclass
class SealedBidAuctionRecord:
    """Internal state of a single auction session."""

    announcement: TaskAnnouncement
    bids: dict[str, Bid] = field(default_factory=dict)  # bid_id -> Bid
    closed: bool = False
    award: TaskAward | None = None
    rejections: list[BidRejection] = field(default_factory=list)
    ranked_bids: list[tuple[Bid, float]] = field(default_factory=list)


class SealedBidAuction:
    """Sealed-Bid Auction Engine collecting bids, unsealing simultaneously, and awarding contracts."""

    def __init__(self, scorer: BidScorer | None = None, default_lease_duration: float = 30.0) -> None:
        self.scorer = scorer or BidScorer()
        self.default_lease_duration = default_lease_duration
        self._auctions: dict[str, SealedBidAuctionRecord] = {}  # task_id -> record

    def create_auction(self, cfp: TaskAnnouncement) -> str:
        """Initialize a new auction for a task announcement."""
        self._auctions[cfp.task_id] = SealedBidAuctionRecord(announcement=cfp)
        logger.info(f"Auction created for task {cfp.task_id} (window={cfp.auction_window}s, sealed={cfp.sealed})")
        return cfp.task_id

    def get_auction(self, task_id: str) -> SealedBidAuctionRecord | None:
        """Get record for a task auction."""
        return self._auctions.get(task_id)

    def submit_bid(self, bid: Bid, current_time: float | None = None) -> bool:
        """Submit a bid to an active auction."""
        record = self._auctions.get(bid.task_id)
        if not record:
            logger.warning(f"Bid rejected: no auction found for task {bid.task_id}")
            return False
        if record.closed:
            logger.warning(f"Bid rejected: auction for task {bid.task_id} is already closed")
            return False
        if not record.announcement.is_window_open(current_time):
            logger.warning(f"Bid rejected: auction window expired for task {bid.task_id}")
            return False

        # If announcement is sealed, bid should be sealed or have commitment hash
        if record.announcement.sealed and not bid.sealed and not bid.commitment_hash:
            bid.sealed = True

        record.bids[bid.bid_id] = bid
        logger.info(f"Bid {bid.bid_id} submitted by node {bid.node_id} for task {bid.task_id}")
        return True

    def reveal_bid(
        self,
        task_id: str,
        bid_id: str,
        salt: str,
        cost: float | None = None,
        estimated_duration: float | None = None,
        capability_score: float | None = None,
    ) -> bool:
        """Unseal a bid by providing the salt and verifying cryptographic commitment."""
        record = self._auctions.get(task_id)
        if not record:
            return False
        bid = record.bids.get(bid_id)
        if not bid:
            return False

        bid.salt = salt
        if cost is not None:
            bid.cost = cost
        if estimated_duration is not None:
            bid.estimated_duration = estimated_duration
        if capability_score is not None:
            bid.capability_score = capability_score

        if bid.commitment_hash:
            if not bid.verify_commitment(salt):
                logger.error(f"Bid commitment verification failed for bid {bid_id}")
                return False

        bid.sealed = False
        return True

    def close_auction(
        self,
        task_id: str,
        node_skills_map: Mapping[str, list[str]] | None = None,
        active_tasks_map: Mapping[str, int] | None = None,
        node_modality_map: Mapping[str, NodeModality | str] | None = None,
        lease_duration: float | None = None,
        current_time: float | None = None,
    ) -> tuple[TaskAward | None, list[BidRejection]]:
        """Close the auction, simultaneously unseal bids, evaluate and return award and rejections."""
        record = self._auctions.get(task_id)
        if not record:
            logger.warning(f"Cannot close auction: task {task_id} not found")
            return None, []
        if record.closed and record.award:
            return record.award, record.rejections

        record.closed = True
        now = time.time() if current_time is None else current_time
        ttl = lease_duration or self.default_lease_duration

        # Simultaneously unseal all submitted bids
        valid_bids: list[Bid] = []
        rejections: list[BidRejection] = []

        for bid in record.bids.values():
            if bid.commitment_hash:
                if not bid.salt:
                    rejections.append(
                        BidRejection(
                            task_id=task_id,
                            node_id=bid.node_id,
                            reason="Sealed bid commitment was never revealed",
                            bid_id=bid.bid_id,
                        )
                    )
                    continue
                if not bid.verify_commitment(bid.salt):
                    rejections.append(
                        BidRejection(
                            task_id=task_id,
                            node_id=bid.node_id,
                            reason="Cryptographic commitment hash mismatch",
                            bid_id=bid.bid_id,
                        )
                    )
                    continue
            # Unseal bid
            bid.sealed = False
            valid_bids.append(bid)

        if not valid_bids:
            record.rejections = rejections
            return None, rejections

        ranked = self.scorer.rank_bids(
            cfp=record.announcement,
            bids=valid_bids,
            node_skills_map=node_skills_map,
            active_tasks_map=active_tasks_map,
            node_modality_map=node_modality_map,
        )
        record.ranked_bids = ranked

        # Best bid with score > 0
        winning_candidate: tuple[Bid, float] | None = None
        for b, score in ranked:
            if score > 0.0:
                winning_candidate = (b, score)
                break

        if not winning_candidate:
            for b, _ in ranked:
                rejections.append(
                    BidRejection(
                        task_id=task_id,
                        node_id=b.node_id,
                        reason="Bid score did not meet minimum threshold",
                        bid_id=b.bid_id,
                    )
                )
            record.rejections = rejections
            return None, rejections

        winner_bid, winner_score = winning_candidate
        lease_id = f"lease-{uuid.uuid4().hex[:8]}"
        award = TaskAward(
            task_id=task_id,
            winning_node_id=winner_bid.node_id,
            lease_id=lease_id,
            lease_duration=ttl,
            awarded_at=now,
            bid_id=winner_bid.bid_id,
            score=winner_score,
        )
        record.award = award

        # Rejections for all other bidders
        for b, score in ranked:
            if b.bid_id != winner_bid.bid_id:
                rejections.append(
                    BidRejection(
                        task_id=task_id,
                        node_id=b.node_id,
                        reason=f"Runner-up proposal (score={score:.4f} vs winning={winner_score:.4f})",
                        bid_id=b.bid_id,
                    )
                )

        record.rejections = rejections
        return award, rejections

    def get_runner_up(self, task_id: str, excluded_node_ids: set[str] | None = None) -> tuple[Bid, float] | None:
        """Retrieve highest scoring runner-up bid excluding specified nodes."""
        record = self._auctions.get(task_id)
        if not record or not record.ranked_bids:
            return None
        excluded = excluded_node_ids or set()
        for b, score in record.ranked_bids:
            if b.node_id not in excluded and score > 0.0:
                return b, score
        return None


class FailoverManager:
    """Manages lease expirations, node liveness, and automated task failover."""

    def __init__(
        self,
        lease_manager: LeaseManager,
        auction_engine: SealedBidAuction,
    ) -> None:
        self.lease_manager = lease_manager
        self.auction_engine = auction_engine
        self.unhealthy_nodes: set[str] = set()
        self.failover_log: list[dict[str, Any]] = []

    def process_expired_leases(
        self,
        coordinator: FleetCoordinator,
        current_time: float | None = None,
    ) -> list[str]:
        """Check expired leases, revoke node health, and re-assign tasks to runner-up or re-auction."""
        now = time.time() if current_time is None else current_time
        expired_leases = self.lease_manager.check_expired_leases(now)
        reassigned_tasks: list[str] = []

        for lease in expired_leases:
            task_id = lease.task_id
            failed_node_id = lease.node_id
            logger.warning(f"Lease expired for task {task_id} held by node {failed_node_id}. Initiating failover.")

            # 1. Mark node unhealthy in coordinator
            self.unhealthy_nodes.add(failed_node_id)
            if failed_node_id in coordinator.nodes:
                coordinator.nodes[failed_node_id].healthy = False
                coordinator.nodes[failed_node_id].active_tasks = max(
                    0, coordinator.nodes[failed_node_id].active_tasks - 1
                )

            # 2. Reclaim expired lease
            self.lease_manager.revoke_lease(task_id)

            # 3. Attempt runner-up failover
            runner_up = self.auction_engine.get_runner_up(task_id=task_id, excluded_node_ids=self.unhealthy_nodes)

            if runner_up:
                runner_bid, runner_score = runner_up
                target_node = coordinator.nodes.get(runner_bid.node_id)

                if target_node and target_node.healthy:
                    new_lease = self.lease_manager.create_lease(
                        task_id=task_id,
                        node_id=runner_bid.node_id,
                        duration=lease.duration,
                        granted_at=now,
                    )
                    target_node.active_tasks += 1

                    # Record new award in auction
                    record = self.auction_engine.get_auction(task_id)
                    if record:
                        record.award = TaskAward(
                            task_id=task_id,
                            winning_node_id=runner_bid.node_id,
                            lease_id=new_lease.lease_id,
                            lease_duration=new_lease.duration,
                            awarded_at=now,
                            bid_id=runner_bid.bid_id,
                            score=runner_score,
                        )

                    log_entry = {
                        "task_id": task_id,
                        "failed_node": failed_node_id,
                        "reassigned_node": runner_bid.node_id,
                        "action": "runner_up_promotion",
                        "timestamp": now,
                    }
                    self.failover_log.append(log_entry)
                    reassigned_tasks.append(task_id)
                    logger.info(f"Task {task_id} successfully failed over to runner-up node {runner_bid.node_id}")
                    continue

            # 4. If no runner-up, re-auction
            record = self.auction_engine.get_auction(task_id)
            if record:
                announcement = record.announcement
                merged_meta = dict(announcement.metadata)
                merged_meta.update(
                    {
                        "failover_retry": True,
                        "previous_failed_node": failed_node_id,
                        "reauction_round": merged_meta.get("reauction_round", 0) + 1,
                        "previous_bids_count": len(record.bids),
                    }
                )
                new_announcement = TaskAnnouncement(
                    task_id=task_id,
                    instruction=announcement.instruction,
                    required_skills=announcement.required_skills,
                    required_modality=announcement.required_modality,
                    deadline=announcement.deadline,
                    budget=announcement.budget,
                    auction_window=announcement.auction_window,
                    sealed=announcement.sealed,
                    created_at=now,
                    metadata=merged_meta,
                )
            else:
                new_announcement = TaskAnnouncement(
                    task_id=task_id,
                    instruction=f"Re-auction for expired task {task_id}",
                    required_skills=[],
                    created_at=now,
                    metadata={"failover_retry": True, "previous_failed_node": failed_node_id, "reauction_round": 1},
                )

            self.auction_engine.create_auction(new_announcement)
            log_entry = {
                "task_id": task_id,
                "failed_node": failed_node_id,
                "action": "re_auction_initiated",
                "timestamp": now,
            }
            self.failover_log.append(log_entry)
            reassigned_tasks.append(task_id)
            logger.info(f"Task {task_id} could not be given to runner-up; initiated re-auction round.")

        return reassigned_tasks
