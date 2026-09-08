"""Unit tests for 2D Occupancy Grid Map rasterization and collision inflation."""

from __future__ import annotations

import math

import pytest

from effero.skills.robotics.grid_map import OccupancyGridMap


def test_grid_map_initialization() -> None:
    grid = OccupancyGridMap(min_x=-5.0, min_y=-5.0, max_x=5.0, max_y=5.0, resolution=0.2)
    assert grid.width_cells == 50
    assert grid.height_cells == 50
    assert not grid.is_occupied(0.0, 0.0)

    with pytest.raises(ValueError, match="Map boundaries"):
        OccupancyGridMap(min_x=5.0, max_x=-5.0)

    with pytest.raises(ValueError, match="Resolution must be positive"):
        OccupancyGridMap(resolution=-0.1)


def test_coordinate_transforms() -> None:
    grid = OccupancyGridMap(min_x=0.0, min_y=0.0, max_x=10.0, max_y=10.0, resolution=1.0)
    gx, gy = grid.world_to_grid(2.3, 4.8)
    assert gx == 2
    assert gy == 4

    wx, wy = grid.grid_to_world(gx, gy)
    assert math.isclose(wx, 2.5, abs_tol=1e-3)
    assert math.isclose(wy, 4.5, abs_tol=1e-3)


def test_rectangular_and_point_obstacles() -> None:
    grid = OccupancyGridMap(min_x=0.0, min_y=0.0, max_x=10.0, max_y=10.0, resolution=0.5)

    # Point obstacle
    grid.set_obstacle(1.0, 1.0)
    assert grid.is_occupied(1.0, 1.0)
    assert not grid.is_occupied(2.0, 2.0)

    # Rectangular obstacle from (3.0, 3.0) to (5.0, 5.0)
    grid.add_rectangular_obstacle(3.0, 3.0, 5.0, 5.0)
    assert grid.is_occupied(3.5, 3.5)
    assert grid.is_occupied(4.5, 4.5)
    assert not grid.is_occupied(6.0, 6.0)


def test_circular_and_line_obstacles() -> None:
    grid = OccupancyGridMap(min_x=0.0, min_y=0.0, max_x=10.0, max_y=10.0, resolution=0.2)

    # Circle at (5.0, 5.0) with radius 1.0
    grid.add_circular_obstacle(5.0, 5.0, radius=1.0)
    assert grid.is_occupied(5.0, 5.0)
    assert grid.is_occupied(5.5, 5.5)  # distance ~0.707m <= 1.0m
    assert not grid.is_occupied(7.0, 7.0)

    # Line from (1.0, 8.0) to (4.0, 8.0)
    grid.add_line_obstacle(1.0, 8.0, 4.0, 8.0)
    assert grid.is_occupied(2.5, 8.0)
    assert not grid.is_occupied(2.5, 9.0)


def test_radial_obstacle_inflation() -> None:
    grid = OccupancyGridMap(min_x=0.0, min_y=0.0, max_x=10.0, max_y=10.0, resolution=0.1)

    # Single point obstacle at (5.0, 5.0)
    grid.set_obstacle(5.0, 5.0)
    # 0.3m away should initially be free
    assert not grid.is_occupied(5.2, 5.0)

    # Inflate by robot radius of 0.3m
    grid.inflate_obstacles(robot_radius=0.3)

    # Now (5.2, 5.0) (0.2m away) must be marked occupied by inflation layer
    assert grid.is_occupied(5.2, 5.0, include_inflated=True)
    # But strictly raw obstacle check remains False
    assert not grid.is_occupied(5.2, 5.0, include_inflated=False)

    # Point 0.5m away should remain free
    assert not grid.is_occupied(5.5, 5.0, include_inflated=True)


def test_line_of_sight_raycasting() -> None:
    grid = OccupancyGridMap(min_x=0.0, min_y=0.0, max_x=10.0, max_y=10.0, resolution=0.2)

    # Completely clear
    assert grid.is_line_clear(1.0, 1.0, 8.0, 8.0)

    # Place a wall between (1.0, 1.0) and (8.0, 8.0)
    grid.add_rectangular_obstacle(4.0, 3.0, 6.0, 6.0)
    assert not grid.is_line_clear(1.0, 1.0, 8.0, 8.0)

    # Line of sight parallel to wall should still be clear
    assert grid.is_line_clear(1.0, 1.0, 1.0, 8.0)


def test_serialization() -> None:
    grid = OccupancyGridMap(min_x=-2.0, min_y=-2.0, max_x=2.0, max_y=2.0, resolution=0.5)
    grid.set_obstacle(0.0, 0.0)
    meta = grid.to_dict()
    assert meta["resolution"] == 0.5
    assert meta["width_cells"] == 8
    assert meta["obstacle_cells_count"] == 1
