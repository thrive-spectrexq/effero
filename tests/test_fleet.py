"""Tests for Multi-Agent Fleet Coordinator."""
from __future__ import annotations

import pytest

from effero.core.fleet.coordinator import FleetCoordinator, FleetNode
from effero.protocols.a2a import AgentCard, TaskMessage, TaskState


def test_fleet_registration_and_discovery() -> None:
    coordinator = FleetCoordinator()

    card1 = AgentCard(
        name="mobile-base-1",
        description="Mobile delivery rover",
        endpoint="http://192.168.1.50:8000",
        skills=["robotics.navigate.go_to", "robotics.navigate.stop"],
    )
    card2 = AgentCard(
        name="manipulator-arm-1",
        description="6-DOF tabletop arm",
        endpoint="http://192.168.1.51:8000",
        skills=["robotics.arm.move_to", "robotics.arm.pick_place"],
    )

    node1 = coordinator.register_node(card1)
    node2 = coordinator.register_node(card2)

    assert len(coordinator.nodes) == 2
    assert coordinator.nodes["mobile-base-1"].id == "mobile-base-1"

    # Capability-based node selection
    selected_for_nav = coordinator.select_best_node(["robotics.navigate.go_to"])
    assert selected_for_nav is not None
    assert selected_for_nav.id == "mobile-base-1"

    selected_for_arm = coordinator.select_best_node(["robotics.arm.pick_place"])
    assert selected_for_arm is not None
    assert selected_for_arm.id == "manipulator-arm-1"


def test_shared_state_broadcasting() -> None:
    coordinator = FleetCoordinator()
    coordinator.set_shared_fact("target_object_detected", {"class": "cup", "x": 1.5, "y": 0.5})

    val = coordinator.get_shared_fact("target_object_detected")
    assert val is not None
    assert val["class"] == "cup"
