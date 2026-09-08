"""Unit tests for Pure Pursuit path tracking controller."""

from __future__ import annotations

import math

from effero.skills.robotics.tracking.pure_pursuit import (
    PurePursuitController,
    PurePursuitParams,
)


def test_pure_pursuit_straight_line_following() -> None:
    controller = PurePursuitController(PurePursuitParams(target_speed_mps=0.8))

    # Path along x-axis from (0, 0) to (10, 0)
    waypoints = [(float(i), 0.0) for i in range(11)]

    cmd = controller.compute_command(
        current_x=0.0,
        current_y=0.0,
        current_yaw=0.0,
        current_speed=0.5,
        waypoints=waypoints,
    )

    assert cmd["goal_reached"] is False
    assert cmd["linear_velocity"] > 0.0
    # On straight line facing path, angular velocity should be approximately zero
    assert math.isclose(cmd["angular_velocity"], 0.0, abs_tol=0.05)
    assert cmd["distance_to_goal"] == 10.0


def test_pure_pursuit_steers_towards_offset_path() -> None:
    controller = PurePursuitController()

    # Path along y = 2.0
    waypoints = [(float(i), 2.0) for i in range(10)]

    # Robot is at (0, 0) heading straight along x-axis (yaw = 0.0)
    # The path is to the robot's left (positive y)
    cmd = controller.compute_command(
        current_x=0.0,
        current_y=0.0,
        current_yaw=0.0,
        current_speed=0.5,
        waypoints=waypoints,
    )

    # Robot should steer left (positive angular velocity) to intercept path
    assert cmd["angular_velocity"] > 0.1
    assert cmd["goal_reached"] is False


def test_pure_pursuit_goal_reached_stopping() -> None:
    controller = PurePursuitController(PurePursuitParams(goal_tolerance_m=0.2))

    waypoints = [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]

    # Robot positioned at (1.95, 1.95), within 0.2m of final waypoint (2.0, 2.0)
    cmd = controller.compute_command(
        current_x=1.95,
        current_y=1.95,
        current_yaw=math.pi / 4,
        current_speed=0.2,
        waypoints=waypoints,
    )

    assert cmd["goal_reached"] is True
    assert cmd["linear_velocity"] == 0.0
    assert cmd["angular_velocity"] == 0.0


def test_pure_pursuit_empty_waypoints_safe_handling() -> None:
    controller = PurePursuitController()
    cmd = controller.compute_command(0.0, 0.0, 0.0, 0.0, waypoints=[])
    assert cmd["goal_reached"] is True
    assert cmd["linear_velocity"] == 0.0
    assert cmd["angular_velocity"] == 0.0
