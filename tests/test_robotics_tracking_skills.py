"""Integration tests for NavigationController tracking skills and DWA/Pure Pursuit skills."""

from __future__ import annotations

import pytest

from effero.skills.robotics.navigate import (
    NavigationController,
    compute_velocity,
    track_path,
)


@pytest.mark.asyncio
async def test_compute_velocity_skill_dwa() -> None:
    res = await compute_velocity(
        goal_x=3.0,
        goal_y=0.0,
        obstacles=[(1.5, 0.0)],
    )

    assert "linear_velocity" in res
    assert "angular_velocity" in res
    assert "predicted_trajectory" in res
    assert res["goal"] == [3.0, 0.0]
    assert len(res["predicted_trajectory"]) > 0


@pytest.mark.asyncio
async def test_track_path_skill_pure_pursuit() -> None:
    waypoints = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]

    res = await track_path(waypoints=waypoints)

    assert "linear_velocity" in res
    assert "angular_velocity" in res
    assert "goal_reached" in res
    assert res["goal_reached"] is False
    assert res["distance_to_goal"] > 0.0


def test_navigation_controller_tracking_methods() -> None:
    controller = NavigationController()
    controller.pose.x = 0.0
    controller.pose.y = 0.0

    dwa_res = controller.compute_dwa_velocity(goal_x=2.0, goal_y=2.0)
    assert dwa_res["linear_velocity"] > 0.0

    pp_res = controller.track_waypoints(waypoints=[(0.0, 0.0), (2.0, 2.0)])
    assert pp_res["goal_reached"] is False
