"""Benchmark for A* 2D grid path planning."""

from __future__ import annotations

from typing import Any

import pytest

from effero.skills.robotics.grid_map import OccupancyGridMap
from effero.skills.robotics.planning.a_star import AStarPlanner


@pytest.fixture
def grid_map_with_obstacles() -> OccupancyGridMap:
    grid = OccupancyGridMap(min_x=0.0, min_y=0.0, max_x=10.0, max_y=10.0, resolution=0.1)
    # Add vertical barrier wall with door opening
    grid.add_rectangular_obstacle(4.8, 0.0, 5.2, 7.0)
    grid.add_rectangular_obstacle(4.8, 8.0, 5.2, 10.0)
    return grid


def test_bench_a_star_planning(benchmark: Any, grid_map_with_obstacles: OccupancyGridMap) -> None:
    """Benchmark A* path search across 100x100 grid around barrier."""
    planner = AStarPlanner(grid_map_with_obstacles)

    def plan_path():
        return planner.plan(start_x=1.0, start_y=1.0, goal_x=9.0, goal_y=9.0, smooth=True)

    result = benchmark(plan_path)
    assert result is not None
    assert len(result.waypoints) >= 3
