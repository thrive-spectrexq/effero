"""Comprehensive test suite for Multi-Agent Fleet Consensus, Sealed-Bid Auctions, and Failover."""

from __future__ import annotations

from effero.core.fleet.auction import (
    Bid,
    BidScorer,
    CallForProposals,
    LeaseManager,
    NodeModality,
    SealedBidAuction,
    TaskAnnouncement,
    TaskLease,
)
from effero.core.fleet.coordinator import FleetCoordinator
from effero.protocols.a2a import AgentCard


def test_node_modality_enum_and_normalization() -> None:
    """Test all NodeModality enum members and normalization logic."""
    assert NodeModality.ROBOTICS.value == "robotics"
    assert NodeModality.VISION_COMPUTE.value == "vision_compute"
    assert NodeModality.IOT_EDGE.value == "iot_edge"
    assert NodeModality.DESKTOP_AUTOMATION.value == "desktop_automation"
    assert NodeModality.CLOUD_REASONING.value == "cloud_reasoning"

    # String parsing and normalization
    assert NodeModality.from_str("robotics") == NodeModality.ROBOTICS
    assert NodeModality.from_str("ROBOTICS") == NodeModality.ROBOTICS
    assert NodeModality.from_str(" vision_compute ") == NodeModality.VISION_COMPUTE
    assert NodeModality.from_str("IoT_Edge") == NodeModality.IOT_EDGE
    assert NodeModality.from_str(None) is None
    assert NodeModality.from_str("unknown_modality") is None


def test_task_announcement_creation_and_window_lifecycle() -> None:
    """Test TaskAnnouncement / CallForProposals window opening and closing."""
    assert CallForProposals is TaskAnnouncement

    base_time = 1000.0
    cfp = TaskAnnouncement(
        task_id="task-100",
        instruction="Inspect turbine bearings",
        required_skills=["vision.inspect"],
        required_modality=NodeModality.ROBOTICS,
        auction_window=5.0,
        created_at=base_time,
    )

    assert cfp.task_id == "task-100"
    assert cfp.is_window_open(current_time=1000.0) is True
    assert cfp.is_window_open(current_time=1004.9) is True
    assert cfp.is_window_open(current_time=1005.0) is True
    assert cfp.is_window_open(current_time=1005.1) is False


def test_bid_cryptographic_commitment_hash_verification() -> None:
    """Test SHA-256 commit-reveal hashing and tamper detection for sealed bids."""
    bid = Bid(
        bid_id="bid-001",
        task_id="task-100",
        node_id="node-alpha",
        cost=25.50,
        estimated_duration=3.2,
        capability_score=0.95,
        sealed=True,
    )
    salt = "secure-salt-phrase-987"
    expected_hash = bid.compute_commitment(salt)

    bid.commitment_hash = expected_hash
    assert bid.verify_commitment(salt) is True
    assert bid.verify_commitment("wrong-salt") is False

    # Tampering with bid attributes invalidates the commitment
    bid.cost = 25.51
    assert bid.verify_commitment(salt) is False


def test_bid_scorer_skill_match_coverage_gradient() -> None:
    """Test scoring gradient based on required skill coverage."""
    scorer = BidScorer()
    cfp = TaskAnnouncement(
        task_id="task-1",
        instruction="Full warehouse inventory cycle",
        required_skills=["robotics.navigate", "vision.detect", "manipulation.pick"],
    )

    bid_none = Bid(
        bid_id="b0",
        task_id="task-1",
        node_id="n0",
        skills=["unrelated.skill"],
        cost=10.0,
        estimated_duration=1.0,
    )
    bid_partial = Bid(
        bid_id="b1",
        task_id="task-1",
        node_id="n1",
        skills=["robotics.navigate"],
        cost=10.0,
        estimated_duration=1.0,
    )
    bid_all = Bid(
        bid_id="b2",
        task_id="task-1",
        node_id="n2",
        skills=["robotics.navigate", "vision.detect", "manipulation.pick"],
        cost=10.0,
        estimated_duration=1.0,
    )

    s_none = scorer.score_bid(cfp, bid_none)
    s_partial = scorer.score_bid(cfp, bid_partial)
    s_all = scorer.score_bid(cfp, bid_all)

    assert s_all > s_partial > s_none


def test_bid_scorer_queue_depth_workload_penalty() -> None:
    """Test that higher active task queue depths decrease bid scores."""
    scorer = BidScorer()
    cfp = TaskAnnouncement(task_id="task-2", instruction="Execute test run")

    bid_idle = Bid(bid_id="b-idle", task_id="task-2", node_id="n-idle", queue_depth=0, cost=5.0, estimated_duration=1.0)
    bid_busy = Bid(bid_id="b-busy", task_id="task-2", node_id="n-busy", queue_depth=4, cost=5.0, estimated_duration=1.0)

    s_idle = scorer.score_bid(cfp, bid_idle)
    s_busy = scorer.score_bid(cfp, bid_busy)

    assert s_idle > s_busy


def test_bid_scorer_duration_and_latency_penalty() -> None:
    """Test that lower estimated durations yield higher scores."""
    scorer = BidScorer()
    cfp = TaskAnnouncement(task_id="task-3", instruction="Real-time control packet delivery")

    bid_fast = Bid(bid_id="b-fast", task_id="task-3", node_id="n1", estimated_duration=0.2, cost=5.0)
    bid_slow = Bid(bid_id="b-slow", task_id="task-3", node_id="n2", estimated_duration=15.0, cost=5.0)

    assert scorer.score_bid(cfp, bid_fast) > scorer.score_bid(cfp, bid_slow)


def test_bid_scorer_budget_and_cost_penalties() -> None:
    """Test cost scoring against task budget."""
    scorer = BidScorer()
    cfp = TaskAnnouncement(
        task_id="task-4",
        instruction="Compute neural embeddings",
        budget=100.0,
    )

    bid_cheap = Bid(bid_id="b1", task_id="task-4", node_id="n1", cost=20.0, estimated_duration=1.0)
    bid_expensive = Bid(bid_id="b2", task_id="task-4", node_id="n2", cost=95.0, estimated_duration=1.0)
    bid_over_budget = Bid(bid_id="b3", task_id="task-4", node_id="n3", cost=150.0, estimated_duration=1.0)

    s_cheap = scorer.score_bid(cfp, bid_cheap)
    s_exp = scorer.score_bid(cfp, bid_expensive)
    s_over = scorer.score_bid(cfp, bid_over_budget)

    assert s_cheap > s_exp > s_over


def test_bid_scorer_modality_matching_bonus() -> None:
    """Test hardware modality match bonus and mismatch penalty."""
    scorer = BidScorer()
    cfp = TaskAnnouncement(
        task_id="task-5",
        instruction="Real-time object detection",
        required_modality=NodeModality.VISION_COMPUTE,
    )

    bid_vision = Bid(
        bid_id="b-vis",
        task_id="task-5",
        node_id="n-vis",
        modality=NodeModality.VISION_COMPUTE,
        cost=10.0,
        estimated_duration=1.0,
    )
    bid_desktop = Bid(
        bid_id="b-desk",
        task_id="task-5",
        node_id="n-desk",
        modality=NodeModality.DESKTOP_AUTOMATION,
        cost=10.0,
        estimated_duration=1.0,
    )

    assert scorer.score_bid(cfp, bid_vision) > scorer.score_bid(cfp, bid_desktop)


def test_bid_scorer_strict_modality_rejection() -> None:
    """Test strict modality enforcement where mismatches return score 0.0."""
    scorer = BidScorer(strict_modality=True)
    cfp = TaskAnnouncement(
        task_id="task-6",
        instruction="Physical door manipulation",
        required_modality=NodeModality.ROBOTICS,
    )

    bid_robot = Bid(
        bid_id="b1",
        task_id="task-6",
        node_id="n1",
        modality=NodeModality.ROBOTICS,
        skills=["robotics.arm.manipulate"],
    )
    bid_cloud = Bid(
        bid_id="b2",
        task_id="task-6",
        node_id="n2",
        modality=NodeModality.CLOUD_REASONING,
        skills=["robotics.arm.manipulate"],
    )

    assert scorer.score_bid(cfp, bid_robot) > 0.0
    assert scorer.score_bid(cfp, bid_cloud) == 0.0


def test_bid_scorer_strict_skills_rejection() -> None:
    """Test strict skill enforcement requiring 100% skill coverage."""
    scorer = BidScorer(strict_skills=True)
    cfp = TaskAnnouncement(
        task_id="task-7",
        instruction="Multi-discipline inspection",
        required_skills=["skill.a", "skill.b"],
    )

    bid_partial = Bid(bid_id="b1", task_id="task-7", node_id="n1", skills=["skill.a"])
    bid_full = Bid(bid_id="b2", task_id="task-7", node_id="n2", skills=["skill.a", "skill.b"])

    assert scorer.score_bid(cfp, bid_partial) == 0.0
    assert scorer.score_bid(cfp, bid_full) > 0.0


def test_bid_scorer_rank_bids_ordering() -> None:
    """Test ranking multiple candidate bids in descending score order."""
    scorer = BidScorer()
    cfp = TaskAnnouncement(
        task_id="task-8",
        instruction="Process camera feed",
        required_skills=["vision.detect"],
        budget=50.0,
    )

    b1 = Bid(
        bid_id="b1",
        task_id="task-8",
        node_id="n1",
        skills=["vision.detect"],
        cost=15.0,
        estimated_duration=0.5,
    )
    b2 = Bid(
        bid_id="b2",
        task_id="task-8",
        node_id="n2",
        skills=["vision.detect"],
        cost=45.0,
        estimated_duration=2.0,
    )
    b3 = Bid(bid_id="b3", task_id="task-8", node_id="n3", skills=[], cost=50.0, estimated_duration=5.0)

    ranked = scorer.rank_bids(cfp, [b2, b3, b1])
    assert len(ranked) == 3
    assert ranked[0][0].bid_id == "b1"
    assert ranked[1][0].bid_id == "b2"
    assert ranked[2][0].bid_id == "b3"
    assert ranked[0][1] >= ranked[1][1] >= ranked[2][1]


def test_sealed_bid_auction_submission_within_window() -> None:
    """Test submitting sealed bids to an active auction session."""
    engine = SealedBidAuction()
    cfp = TaskAnnouncement(
        task_id="task-9",
        instruction="Navigate corridor",
        auction_window=10.0,
        created_at=100.0,
        sealed=True,
    )
    engine.create_auction(cfp)

    bid = Bid(
        bid_id="bid-1",
        task_id="task-9",
        node_id="rover-1",
        cost=20.0,
        sealed=True,
    )
    ok = engine.submit_bid(bid, current_time=105.0)
    assert ok is True

    record = engine.get_auction("task-9")
    assert record is not None
    assert "bid-1" in record.bids


def test_sealed_bid_auction_submission_rejected_after_window_expires() -> None:
    """Test that submissions arriving after the auction window expires are rejected."""
    engine = SealedBidAuction()
    cfp = TaskAnnouncement(
        task_id="task-10",
        instruction="Desktop scraping",
        auction_window=3.0,
        created_at=200.0,
    )
    engine.create_auction(cfp)

    bid = Bid(bid_id="bid-late", task_id="task-10", node_id="node-late")
    ok = engine.submit_bid(bid, current_time=203.5)
    assert ok is False


def test_sealed_bid_auction_submission_rejected_for_unknown_or_closed_task() -> None:
    """Test bid submission rejection for non-existent or closed auctions."""
    engine = SealedBidAuction()
    bid_unknown = Bid(bid_id="b1", task_id="non-existent", node_id="n1")
    assert engine.submit_bid(bid_unknown) is False

    cfp = TaskAnnouncement(task_id="task-11", instruction="Run test", auction_window=10.0)
    engine.create_auction(cfp)
    engine.close_auction("task-11")

    bid_closed = Bid(bid_id="b2", task_id="task-11", node_id="n1")
    assert engine.submit_bid(bid_closed) is False


def test_sealed_bid_simultaneous_unsealing_and_award() -> None:
    """Test simultaneous unsealing of all bids upon auction close and issuing awards."""
    engine = SealedBidAuction()
    cfp = TaskAnnouncement(
        task_id="task-12",
        instruction="Edge sensor aggregation",
        required_skills=["iot.read_sensor"],
        auction_window=5.0,
        sealed=True,
    )
    engine.create_auction(cfp)

    b1 = Bid(
        bid_id="bid-win",
        task_id="task-12",
        node_id="node-iot-1",
        skills=["iot.read_sensor"],
        cost=5.0,
        estimated_duration=0.5,
        sealed=True,
    )
    b2 = Bid(
        bid_id="bid-lose",
        task_id="task-12",
        node_id="node-iot-2",
        skills=[],
        cost=25.0,
        estimated_duration=4.0,
        sealed=True,
    )

    engine.submit_bid(b1)
    engine.submit_bid(b2)

    award, rejections = engine.close_auction(task_id="task-12", lease_duration=45.0)

    assert award is not None
    assert award.task_id == "task-12"
    assert award.winning_node_id == "node-iot-1"
    assert award.lease_duration == 45.0
    assert award.bid_id == "bid-win"

    assert len(rejections) == 1
    assert rejections[0].node_id == "node-iot-2"
    assert "Runner-up" in rejections[0].reason

    # Verify both bids were unsealed
    record = engine.get_auction("task-12")
    assert record is not None
    assert record.bids["bid-win"].sealed is False
    assert record.bids["bid-lose"].sealed is False


def test_sealed_bid_cryptographic_commitment_mismatch_rejected() -> None:
    """Test that a bid with an invalid cryptographic commitment is rejected on unsealing."""
    engine = SealedBidAuction()
    cfp = TaskAnnouncement(task_id="task-13", instruction="Cryptographic auction test", sealed=True)
    engine.create_auction(cfp)

    bid = Bid(
        bid_id="bid-crypto",
        task_id="task-13",
        node_id="node-fraud",
        cost=10.0,
        estimated_duration=1.0,
        sealed=True,
    )
    # Compute genuine commitment
    genuine_salt = "salt-original"
    bid.commitment_hash = bid.compute_commitment(genuine_salt)
    # But tamper with salt or payload
    bid.salt = "tampered-salt"

    engine.submit_bid(bid)
    award, rejections = engine.close_auction("task-13")

    assert award is None
    assert len(rejections) == 1
    assert "commitment hash mismatch" in rejections[0].reason.lower()


def test_task_lease_ttl_expiry_and_active_check() -> None:
    """Test TaskLease TTL calculation and expiration boundary."""
    lease = TaskLease(
        lease_id="lease-001",
        task_id="task-14",
        node_id="node-worker",
        granted_at=500.0,
        duration=30.0,
        last_heartbeat=500.0,
    )

    assert lease.is_expired(current_time=500.0) is False
    assert lease.is_expired(current_time=529.9) is False
    assert lease.is_expired(current_time=530.0) is False
    assert lease.is_expired(current_time=530.1) is True


def test_lease_manager_renewal_and_extension() -> None:
    """Test LeaseManager lease creation, heartbeat renewal, and duration extension."""
    lm = LeaseManager(default_duration=20.0)
    lease = lm.create_lease(task_id="task-15", node_id="worker-1", granted_at=100.0)

    assert lease.duration == 20.0
    assert lm.get_lease("task-15") is not None

    # Heartbeat at t=115.0 with extension to 40.0s
    renew_ok = lm.renew_lease(task_id="task-15", node_id="worker-1", extension=40.0, current_time=115.0)
    assert renew_ok is True

    # At t=130.0, without extension this would have expired (100 + 20 = 120),
    # but with extension from 115.0 with duration 40.0, it remains active until 155.0
    assert lease.is_expired(current_time=130.0) is False
    assert lease.is_expired(current_time=155.1) is True


def test_lease_manager_renewal_security_checks() -> None:
    """Test that unauthorized nodes cannot renew another node's lease, and expired leases fail."""
    lm = LeaseManager(default_duration=10.0)
    lm.create_lease(task_id="task-16", node_id="authorized-node", granted_at=100.0)

    # Wrong node
    assert lm.renew_lease(task_id="task-16", node_id="imposter-node", current_time=102.0) is False

    # Non-existent task
    assert lm.renew_lease(task_id="ghost-task", node_id="authorized-node", current_time=102.0) is False

    # Expired lease
    assert lm.renew_lease(task_id="task-16", node_id="authorized-node", current_time=115.0) is False


def test_failover_manager_detects_expired_lease_and_marks_node_unhealthy() -> None:
    """Test that lease expiry triggers node health revocation and lease reclamation."""
    coordinator = FleetCoordinator()
    card = AgentCard(
        name="flaky-node",
        description="Node prone to disconnects",
        endpoint="http://10.0.0.1:8000",
        skills=["general.compute"],
    )
    coordinator.register_node(card)

    coordinator.lease_manager.create_lease(task_id="task-17", node_id="flaky-node", duration=15.0, granted_at=100.0)
    coordinator.nodes["flaky-node"].active_tasks = 1

    assert coordinator.nodes["flaky-node"].healthy is True
    assert coordinator.lease_manager.get_lease("task-17") is not None

    # Advance time past TTL
    reassigned = coordinator.check_leases_and_failover(current_time=120.0)

    assert "task-17" in reassigned
    assert coordinator.nodes["flaky-node"].healthy is False
    assert coordinator.lease_manager.get_lease("task-17") is None
    assert "flaky-node" in coordinator.failover_manager.unhealthy_nodes


def test_failover_manager_reassigns_to_runner_up_node() -> None:
    """Test automatic task reassignment to healthy runner-up node when primary times out."""
    coordinator = FleetCoordinator()
    card1 = AgentCard(
        name="primary-arm",
        description="Primary robot arm",
        endpoint="http://10.0.0.1:8000",
        skills=["robotics.arm.pick"],
    )
    card2 = AgentCard(
        name="backup-arm",
        description="Backup robot arm",
        endpoint="http://10.0.0.2:8000",
        skills=["robotics.arm.pick"],
    )
    coordinator.register_node(card1)
    coordinator.register_node(card2)

    cfp = TaskAnnouncement(
        task_id="task-18",
        instruction="Pick circuit board",
        required_skills=["robotics.arm.pick"],
        auction_window=5.0,
        created_at=100.0,
    )
    coordinator.announce_task(cfp)

    # Primary bid is better than backup bid
    coordinator.submit_bid(
        Bid(
            bid_id="b-prim",
            task_id="task-18",
            node_id="primary-arm",
            skills=["robotics.arm.pick"],
            cost=10.0,
            estimated_duration=1.0,
        ),
        current_time=101.0,
    )
    coordinator.submit_bid(
        Bid(
            bid_id="b-back",
            task_id="task-18",
            node_id="backup-arm",
            skills=["robotics.arm.pick"],
            cost=20.0,
            estimated_duration=2.0,
        ),
        current_time=101.0,
    )

    # Award to primary
    award = coordinator.evaluate_and_award("task-18", lease_duration=10.0, current_time=102.0)
    assert award is not None
    assert award.winning_node_id == "primary-arm"

    # Time passes; primary fails to renew heartbeat
    reassigned = coordinator.check_leases_and_failover(current_time=115.0)

    assert "task-18" in reassigned
    assert coordinator.nodes["primary-arm"].healthy is False

    # New lease granted to backup-arm
    new_lease = coordinator.lease_manager.get_lease("task-18")
    assert new_lease is not None
    assert new_lease.node_id == "backup-arm"

    # Failover log check
    log = coordinator.failover_manager.failover_log
    assert len(log) > 0
    assert log[-1]["action"] == "runner_up_promotion"
    assert log[-1]["failed_node"] == "primary-arm"
    assert log[-1]["reassigned_node"] == "backup-arm"


def test_failover_manager_initiates_reauction_when_no_runner_up() -> None:
    """Test that task is put up for re-auction when no healthy runner-up exists."""
    coordinator = FleetCoordinator()
    card = AgentCard(
        name="solo-node",
        description="Single edge node",
        endpoint="http://10.0.0.1:8000",
        skills=["edge.process"],
    )
    coordinator.register_node(card)

    cfp = TaskAnnouncement(
        task_id="task-19",
        instruction="Edge processing",
        auction_window=5.0,
        created_at=200.0,
    )
    coordinator.announce_task(cfp)
    coordinator.submit_bid(
        Bid(bid_id="b-solo", task_id="task-19", node_id="solo-node", cost=5.0),
        current_time=201.0,
    )

    award = coordinator.evaluate_and_award("task-19", lease_duration=10.0, current_time=202.0)
    assert award is not None
    assert award.winning_node_id == "solo-node"

    # Solo node expires
    reassigned = coordinator.check_leases_and_failover(current_time=220.0)

    assert "task-19" in reassigned
    assert coordinator.nodes["solo-node"].healthy is False

    log = coordinator.failover_manager.failover_log
    assert len(log) > 0
    assert log[-1]["action"] == "re_auction_initiated"
    assert log[-1]["failed_node"] == "solo-node"


def test_fleet_coordinator_end_to_end_auction_workflow() -> None:
    """Full end-to-end test of task announcement, multi-node bidding, evaluation, and lease renewal."""
    coordinator = FleetCoordinator()

    n1 = coordinator.register_node(
        AgentCard(
            name="robot-base",
            description="Mobile robotics base",
            endpoint="http://192.168.1.10:8000",
            skills=["robotics.navigate"],
        )
    )
    n2 = coordinator.register_node(
        AgentCard(
            name="vision-core",
            description="High-compute vision workstation",
            endpoint="http://192.168.1.20:8000",
            skills=["vision.detect", "vision.track"],
        )
    )

    assert n1.modality == NodeModality.ROBOTICS
    assert n2.modality == NodeModality.VISION_COMPUTE

    # Announce task targeted at vision compute
    task_id = coordinator.announce_task(
        instruction="Detect obstacles in corridor",
        required_skills=["vision.detect"],
        required_modality=NodeModality.VISION_COMPUTE,
        budget=100.0,
        auction_window=5.0,
    )

    coordinator.submit_bid(
        Bid(
            bid_id="b-nav",
            task_id=task_id,
            node_id="robot-base",
            skills=["robotics.navigate"],
            cost=20.0,
            modality=NodeModality.ROBOTICS,
        )
    )
    coordinator.submit_bid(
        Bid(
            bid_id="b-vis",
            task_id=task_id,
            node_id="vision-core",
            skills=["vision.detect"],
            cost=25.0,
            modality=NodeModality.VISION_COMPUTE,
        )
    )

    award = coordinator.evaluate_and_award(task_id, lease_duration=30.0)
    assert award is not None
    assert award.winning_node_id == "vision-core"
    assert coordinator.nodes["vision-core"].active_tasks == 1

    # Heartbeat renewal
    renewed = coordinator.renew_lease(task_id=task_id, node_id="vision-core")
    assert renewed is True


def test_heterogeneous_swarm_modality_specialization_routing() -> None:
    """Test that all 5 modalities route to specialized swarm nodes."""
    coordinator = FleetCoordinator()

    coordinator.register_node(
        AgentCard(
            name="arm-node",
            description="Manipulator",
            endpoint="http://1.1:8000",
            skills=["robotics.arm.reach"],
        ),
        modality=NodeModality.ROBOTICS,
    )
    coordinator.register_node(
        AgentCard(
            name="cam-node",
            description="Vision station",
            endpoint="http://1.2:8000",
            skills=["vision.yolo"],
        ),
        modality=NodeModality.VISION_COMPUTE,
    )
    coordinator.register_node(
        AgentCard(
            name="sensor-node",
            description="IoT edge hub",
            endpoint="http://1.3:8000",
            skills=["iot.read"],
        ),
        modality=NodeModality.IOT_EDGE,
    )
    coordinator.register_node(
        AgentCard(
            name="desktop-node",
            description="Office PC",
            endpoint="http://1.4:8000",
            skills=["desktop.click"],
        ),
        modality=NodeModality.DESKTOP_AUTOMATION,
    )
    coordinator.register_node(
        AgentCard(
            name="cloud-node",
            description="Large LLM Server",
            endpoint="http://1.5:8000",
            skills=["cloud.reason"],
        ),
        modality=NodeModality.CLOUD_REASONING,
    )

    assert (
        coordinator.select_best_node(["robotics.arm.reach"], required_modality=NodeModality.ROBOTICS).id == "arm-node"
    )
    assert coordinator.select_best_node(["vision.yolo"], required_modality=NodeModality.VISION_COMPUTE).id == "cam-node"
    assert coordinator.select_best_node(["iot.read"], required_modality=NodeModality.IOT_EDGE).id == "sensor-node"
    assert (
        coordinator.select_best_node(["desktop.click"], required_modality=NodeModality.DESKTOP_AUTOMATION).id
        == "desktop-node"
    )
    assert (
        coordinator.select_best_node(["cloud.reason"], required_modality=NodeModality.CLOUD_REASONING).id
        == "cloud-node"
    )


def test_fleet_coordinator_unregister_node_cleans_up_leases() -> None:
    """Test unregistering a node revokes all active leases held by that node."""
    coordinator = FleetCoordinator()
    card = AgentCard(
        name="retiring-node",
        description="Node to decommission",
        endpoint="http://10.0.0.5:8000",
        skills=["compute"],
    )
    coordinator.register_node(card)

    coordinator.lease_manager.create_lease(task_id="task-retire", node_id="retiring-node")
    assert coordinator.lease_manager.get_lease("task-retire") is not None

    unregistered = coordinator.unregister_node("retiring-node")
    assert unregistered is True
    assert "retiring-node" not in coordinator.nodes
    assert coordinator.lease_manager.get_lease("task-retire") is None
