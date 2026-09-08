"""Integration tests for NavigationController path planning and robotics.navigate.plan_path skill."""

from __future__ import annotations

import pytest

from effero.skills.robotics.grid_map import OccupancyGridMap
from effero.skills.robotics.navigate import NavigationController, plan_path


@pytest.mark.asyncio
async def test_navigation_controller_plan_path() -> None:
    controller = NavigationController()

    # Plan with default clear map
    res = controller.plan_path_to(target_x=3.0, target_y=3.0)
    assert res["status"] == "success"
    assert res["target"] == [3.0, 3.0]
    assert len(res["waypoints"]) >= 2
    assert res["total_distance_m"] > 0.0


@pytest.mark.asyncio
async def test_navigation_controller_with_custom_map() -> None:
    controller = NavigationController()
    custom_map = OccupancyGridMap(min_x=-5.0, min_y=-5.0, max_x=5.0, max_y=5.0, resolution=0.2)

    # Place wall between (0, 0) and (2, 2)
    custom_map.add_rectangular_obstacle(0.8, -1.0, 1.2, 3.0)
    controller.set_grid_map(custom_map, robot_radius_m=0.2)

    res = controller.plan_path_to(target_x=2.0, target_y=1.0)
    assert res["status"] == "success"

    # Wall must be circumvented: waypoints must detour either above y=3.0 or below y=-1.0
    y_coords = [wp[1] for wp in res["waypoints"]]
    assert max(y_coords) > 3.0 or min(y_coords) < -1.0


@pytest.mark.asyncio
async def test_plan_path_skill_with_dynamic_obstacles() -> None:
    # Test top-level plan_path skill with obstacles parameter
    obstacles = [
        {"type": "rectangle", "min_x": 1.0, "min_y": -2.0, "max_x": 1.4, "max_y": 2.0},
        {"type": "circle", "x": 3.0, "y": 0.0, "radius": 0.5},
    ]

    res = await plan_path(
        target_x=4.0,
        target_y=0.0,
        start_x=0.0,
        start_y=0.0,
        obstacles=obstacles,
        robot_radius_m=0.15,
    )

    assert res["status"] == "success"
    assert res["start"] == [0.0, 0.0]
    assert res["target"] == [4.0, 0.0]
    assert len(res["waypoints"]) >= 2
    assert res["total_distance_m"] > 4.0  # Must be longer than straight line due to detours


@pytest.mark.asyncio
async def test_plan_path_skill_blocked_target() -> None:
    obstacles = [{"type": "rectangle", "min_x": 1.0, "min_y": 1.0, "max_x": 3.0, "max_y": 3.0}]

    # Target (2.0, 2.0) is directly inside the obstacle
    res = await plan_path(
        target_x=2.0,
        target_y=2.0,
        start_x=0.0,
        start_y=0.0,
        obstacles=obstacles,
    )

    assert res["status"] == "error"
    assert "No collision-free path found" in res["message"]
