"""Unit tests for Dynamic Window Approach (DWA) obstacle avoidance and trajectory generation."""

from __future__ import annotations

import math

from effero.skills.robotics.tracking.dwa import DWAController, DWAParams, RobotState


def test_dwa_free_field_advances_towards_goal() -> None:
    controller = DWAController(DWAParams())
    state = RobotState(x=0.0, y=0.0, yaw=0.0, v=0.0, omega=0.0)
    goal = (5.0, 0.0)
    obstacles: list[tuple[float, float]] = []

    v, omega, traj = controller.compute_velocity(state, goal, obstacles)

    # In open field straight ahead, robot should accelerate forward with near zero angular rate
    assert v > 0.0
    assert abs(omega) < 0.1
    assert len(traj) > 1
    # Final point of predicted trajectory should move along positive x
    assert traj[-1][0] > 0.0


def test_dwa_avoids_obstacle_in_path() -> None:
    params = DWAParams(robot_radius=0.25)
    controller = DWAController(params)

    # Robot at origin facing (1, 0)
    state = RobotState(x=0.0, y=0.0, yaw=0.0, v=0.4, omega=0.0)
    goal = (4.0, 0.0)

    # Obstacle placed directly ahead at (1.5, 0.0)
    obstacles = [(1.5, 0.0)]

    v, omega, traj = controller.compute_velocity(state, goal, obstacles)

    # Robot must steer left or right to avoid direct collision
    assert abs(omega) > 0.05
    # Trajectory should not intersect obstacle circle
    for px, py in traj:
        dist_to_obs = math.hypot(px - 1.5, py - 0.0)
        assert dist_to_obs >= params.robot_radius - 1e-3


def test_dwa_goal_arrival_halts_motion() -> None:
    controller = DWAController(DWAParams())
    state = RobotState(x=3.0, y=3.0, yaw=0.0, v=0.3, omega=0.0)
    goal = (3.05, 3.05)  # Within 0.15m tolerance

    v, omega, traj = controller.compute_velocity(state, goal, obstacles=[])
    assert v == 0.0
    assert omega == 0.0


def test_dwa_emergency_stop_when_completely_blocked() -> None:
    params = DWAParams(robot_radius=0.3)
    controller = DWAController(params)

    # Robot trapped by dense wall of obstacles in all forward directions
    state = RobotState(x=0.0, y=0.0, yaw=0.0, v=0.0, omega=0.0)
    goal = (5.0, 0.0)
    obstacles = [
        (0.2, -0.4),
        (0.2, -0.2),
        (0.2, 0.0),
        (0.2, 0.2),
        (0.2, 0.4),
        (0.0, 0.4),
        (0.0, -0.4),
    ]

    v, omega, traj = controller.compute_velocity(state, goal, obstacles)
    # When all forward candidates result in collision, safe stop is returned
    assert v == 0.0
    assert omega == 0.0
