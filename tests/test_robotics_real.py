"""Tests for real kinematics and trajectory planning in robotics skills."""

from __future__ import annotations

import math

import pytest

from effero.skills.robotics.arm import (
    ArmKinematicModel,
    home,
    move_to,
    pick_place,
    set_gripper,
)
from effero.skills.robotics.navigate import (
    NavigationController,
    get_position,
    go_to_coords,
    stop,
)


def test_arm_forward_and_inverse_kinematics() -> None:
    model = ArmKinematicModel()

    # Known target within reachable workspace
    target_x = 0.25
    target_y = 0.15
    target_z = 0.20

    joints = model.inverse_kinematics(target_x, target_y, target_z)
    calc_x, calc_y, calc_z = model.forward_kinematics(joints)

    # Verification of analytical closure within sub-millimeter precision
    assert math.isclose(calc_x, target_x, abs_tol=1e-3)
    assert math.isclose(calc_y, target_y, abs_tol=1e-3)
    assert math.isclose(calc_z, target_z, abs_tol=1e-3)


def test_arm_reachability_boundary_checks() -> None:
    model = ArmKinematicModel()

    # Out of reach target (> 0.55m)
    with pytest.raises(ValueError, match="exceeds maximum reach"):
        model.inverse_kinematics(1.5, 1.5, 1.0)

    # Inside minimum singularity zone (< 0.10m)
    with pytest.raises(ValueError, match="within minimum singularity zone"):
        model.inverse_kinematics(0.01, 0.01, 0.15)


@pytest.mark.asyncio
async def test_arm_skills_execution() -> None:
    # Test move_to
    res_move = await move_to(0.25, 0.10, 0.20)
    assert res_move["status"] == "success"
    assert "position" in res_move
    assert "trajectory_duration_seconds" in res_move
    assert res_move["trajectory_duration_seconds"] > 0

    # Test gripper
    res_grip = await set_gripper(open_gripper=False)
    assert res_grip["status"] == "success"
    assert res_grip["gripper_state"] == "closed"

    # Test autonomous home
    res_home = await home()
    assert res_home["status"] == "success"
    assert res_home["state"] == "homed"

    # Test full pick-and-place
    res_pp = await pick_place(0.20, 0.10, 0.15, 0.10, 0.25, 0.15)
    assert res_pp["status"] == "success"
    assert res_pp["stages_executed"] == 9


@pytest.mark.asyncio
async def test_navigation_kinematics_and_waypoint_tracking() -> None:
    nav = NavigationController()

    # Navigate to kitchen (3.5, 1.2) from (0.0, 0.0)
    res = nav.navigate_to_waypoint("kitchen")
    assert res["status"] == "success"
    expected_dist = math.hypot(3.5, 1.2)
    assert math.isclose(res["distance_meters"], expected_dist, abs_tol=1e-2)
    assert res["duration_seconds"] > 0
    assert nav.pose.x == 3.5
    assert nav.pose.y == 1.2

    # Emergency stop
    stop_res = nav.stop()
    assert stop_res["status"] == "success"
    assert nav.emergency_stopped is True

    # Movement blocked when E-stop active
    blocked = nav.navigate_to_waypoint("living_room")
    assert blocked["status"] == "error"

    # Clear stop
    nav.clear_stop()
    assert nav.emergency_stopped is False

    # Move again
    res2 = nav.navigate_to_coordinates(1.0, 1.0, 0.0)
    assert res2["status"] == "success"


@pytest.mark.asyncio
async def test_navigation_skills_registered() -> None:
    res = await go_to_coords(2.0, 1.0, 45.0)
    assert res["status"] == "success"

    telemetry = await get_position()
    assert telemetry["status"] == "success"
    assert "pose" in telemetry
    assert "odometry_total_meters" in telemetry

    halt = await stop()
    assert halt["status"] == "success"
