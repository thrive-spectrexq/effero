"""Integration tests for FleetCoordinator, Agent fleet wiring, and sealed bid rules."""

from __future__ import annotations

import asyncio

import pytest

from effero.config import EfferoConfig, FleetConfig
from effero.core.agent import Agent
from effero.core.event_bus import Event, EventBus
from effero.core.fleet import (
    Bid,
    FleetCoordinator,
    NodeModality,
    TaskAnnouncement,
)
from effero.protocols.a2a import AgentCard


def test_agent_initializes_fleet_when_configured() -> None:
    config = EfferoConfig()
    config.fleet = FleetConfig(enabled=True, default_lease_duration=45.0)
    agent = Agent(config=config)

    assert agent.fleet is not None
    assert agent.fleet.default_lease_duration == 45.0
    assert agent.fleet.event_bus is agent.event_bus


@pytest.mark.asyncio
async def test_fleet_coordinator_broadcasts_cfp_to_event_bus() -> None:
    event_bus = EventBus()
    received_events: list[Event] = []

    async def on_event(ev: Event) -> None:
        received_events.append(ev)

    event_bus.subscribe("fleet.cfp.announced", on_event)

    coordinator = FleetCoordinator(event_bus=event_bus)
    announcement = TaskAnnouncement(
        task_id="task-broadcast-test",
        instruction="Navigate to station 4",
        required_skills=["robotics.navigate"],
        auction_window=10.0,
    )

    tid = coordinator.announce_task(announcement)
    assert tid == "task-broadcast-test"
    await asyncio.sleep(0.02)
    assert len(received_events) == 1
    assert received_events[0].data["task_id"] == "task-broadcast-test"
    assert received_events[0].data["cfp"]["instruction"] == "Navigate to station 4"


def test_evaluate_and_award_lease_id_consistency() -> None:
    coordinator = FleetCoordinator(default_lease_duration=25.0)
    card = AgentCard(
        name="mobile-node",
        description="Mobile Robot",
        endpoint="http://10.0.0.1:8000",
        skills=["robotics.arm.reach"],
    )
    coordinator.register_node(card, modality=NodeModality.ROBOTICS)

    task_id = "task-lease-consistency"
    coordinator.announce_task(
        task_id=task_id,
        instruction="Grasp item",
        required_skills=["robotics.arm.reach"],
        required_modality=NodeModality.ROBOTICS,
        auction_window=5.0,
        sealed=False,
    )

    bid = Bid(
        bid_id="bid-consistency",
        task_id=task_id,
        node_id="mobile-node",
        cost=10.0,
        estimated_duration=5.0,
        capability_score=1.0,
    )
    coordinator.submit_bid(bid)

    award = coordinator.evaluate_and_award(task_id)
    assert award is not None
    assert award.winning_node_id == "mobile-node"

    # Verify lease ID in lease_manager matches the award.lease_id precisely
    lease = coordinator.lease_manager.get_lease(task_id)
    assert lease is not None
    assert lease.lease_id == award.lease_id
    assert lease.duration == 25.0


def test_unrevealed_sealed_bid_is_rejected() -> None:
    coordinator = FleetCoordinator()
    card = AgentCard(
        name="secure-node",
        description="Node with sealed bids",
        endpoint="http://10.0.0.2:8000",
        skills=["vision.detect"],
    )
    coordinator.register_node(card)

    task_id = "task-unrevealed-bid"
    coordinator.announce_task(
        task_id=task_id,
        instruction="Detect objects",
        required_skills=["vision.detect"],
        auction_window=5.0,
        sealed=True,
    )

    # Submit a sealed bid with commitment hash, but NEVER provide the salt
    bid = Bid(
        bid_id="bid-unrevealed",
        task_id=task_id,
        node_id="secure-node",
        cost=5.0,
        estimated_duration=3.0,
        capability_score=0.9,
    )
    bid.commitment_hash = bid.compute_commitment(salt="secret-salt-123")
    bid.salt = None  # Intentionally withhold salt
    coordinator.submit_bid(bid)

    award = coordinator.evaluate_and_award(task_id)
    # Since the single bid was never revealed, it must NOT be awarded
    assert award is None

    auction = coordinator.auction_engine.get_auction(task_id)
    assert auction is not None
    assert len(auction.rejections) == 1
    assert "never revealed" in auction.rejections[0].reason


def test_failover_reauction_preserves_history_and_increments_round() -> None:
    coordinator = FleetCoordinator(default_lease_duration=10.0)
    card = AgentCard(
        name="flaky-node",
        description="Node that will fail",
        endpoint="http://10.0.0.3:8000",
        skills=["iot.temp"],
    )
    coordinator.register_node(card)

    task_id = "task-history-preservation"
    coordinator.announce_task(
        task_id=task_id,
        instruction="Read sensor",
        required_skills=["iot.temp"],
        auction_window=5.0,
        metadata={"initial_meta": "value_1"},
    )

    bid = Bid(
        bid_id="bid-flaky",
        task_id=task_id,
        node_id="flaky-node",
        cost=1.0,
        estimated_duration=1.0,
        capability_score=1.0,
    )
    coordinator.submit_bid(bid)
    coordinator.evaluate_and_award(task_id, lease_duration=5.0, current_time=100.0)

    # Fast forward time to expire lease (t = 110.0 > 100 + 5)
    reassigned = coordinator.check_leases_and_failover(current_time=110.0)
    assert task_id in reassigned

    # Fetch new re-auction and inspect preserved metadata
    reauction = coordinator.auction_engine.get_auction(task_id)
    assert reauction is not None
    assert reauction.announcement.metadata.get("failover_retry") is True
    assert reauction.announcement.metadata.get("previous_failed_node") == "flaky-node"
    assert reauction.announcement.metadata.get("reauction_round") == 1
    assert reauction.announcement.metadata.get("previous_bids_count") == 1
    assert reauction.announcement.metadata.get("initial_meta") == "value_1"
