"""Unit tests for A* 2D grid path planning, obstacle avoidance, and path smoothing."""

from __future__ import annotations

import math

from effero.skills.robotics.grid_map import OccupancyGridMap
from effero.skills.robotics.planning.a_star import AStarPlanner


def test_astar_clear_field_planning() -> None:
    grid = OccupancyGridMap(min_x=0.0, min_y=0.0, max_x=10.0, max_y=10.0, resolution=0.2)
    planner = AStarPlanner(grid)

    start = (1.0, 1.0)
    goal = (8.0, 8.0)

    path = planner.plan(start[0], start[1], goal[0], goal[1], smooth=True)
    assert path is not None
    assert path.is_smoothed is True
    assert len(path.waypoints) >= 2
    assert path.waypoints[0] == start
    assert path.waypoints[-1] == goal

    # In open field with smoothing, smoothed path connects start and goal directly
    straight_line_dist = math.hypot(goal[0] - start[0], goal[1] - start[1])
    assert math.isclose(path.total_distance_m, straight_line_dist, rel_tol=1e-2)


def test_astar_wall_avoidance() -> None:
    grid = OccupancyGridMap(min_x=0.0, min_y=0.0, max_x=10.0, max_y=10.0, resolution=0.2)

    # Erect vertical wall barrier at x in [4.8, 5.2] spanning y from 0 to 7
    grid.add_rectangular_obstacle(4.8, 0.0, 5.2, 7.0)
    grid.inflate_obstacles(robot_radius=0.2)

    planner = AStarPlanner(grid)
    start = (2.0, 3.0)
    goal = (8.0, 3.0)

    path = planner.plan(start[0], start[1], goal[0], goal[1], smooth=True)
    assert path is not None

    # Path must detour around top of wall (y > 7.0)
    max_y = max(pt[1] for pt in path.waypoints)
    assert max_y > 7.0
    assert path.waypoints[0] == start
    assert path.waypoints[-1] == goal

    # Verify no waypoint is inside obstacle
    for wp in path.waypoints:
        assert not grid.is_occupied(wp[0], wp[1], include_inflated=True)


def test_astar_u_shaped_trap_escape() -> None:
    grid = OccupancyGridMap(min_x=0.0, min_y=0.0, max_x=10.0, max_y=10.0, resolution=0.2)

    # Build U-shaped pocket facing right (open towards x > 5)
    # Bottom wall: (2, 2) to (5, 2.4)
    grid.add_rectangular_obstacle(2.0, 2.0, 5.0, 2.4)
    # Left wall: (2, 2) to (2.4, 6)
    grid.add_rectangular_obstacle(2.0, 2.0, 2.4, 6.0)
    # Top wall: (2, 5.6) to (5, 6.0)
    grid.add_rectangular_obstacle(2.0, 5.6, 5.0, 6.0)

    planner = AStarPlanner(grid)
    # Start trapped inside pocket
    start = (3.0, 4.0)
    # Goal outside pocket behind left wall
    goal = (1.0, 4.0)

    path = planner.plan(start[0], start[1], goal[0], goal[1], smooth=False)
    assert path is not None
    assert path.waypoints[0] == start
    assert path.waypoints[-1] == goal

    # Path must exit pocket towards right before rounding back to left
    max_x = max(pt[0] for pt in path.waypoints)
    assert max_x > 5.0


def test_astar_diagonal_corner_cutting_prevention() -> None:
    grid = OccupancyGridMap(min_x=0.0, min_y=0.0, max_x=5.0, max_y=5.0, resolution=1.0)

    # Place two diagonally touching obstacles: at (1, 2) and (2, 1)
    grid.set_obstacle(1.5, 2.5)  # cell (1, 2)
    grid.set_obstacle(2.5, 1.5)  # cell (2, 1)

    planner = AStarPlanner(grid)
    # Try to move through the diagonal bottleneck from (1.5, 1.5) to (2.5, 2.5)
    path = planner.plan(1.5, 1.5, 2.5, 2.5, smooth=False)

    assert path is not None
    # Verify path did not cut diagonally between (1, 2) and (2, 1)
    for i in range(len(path.waypoints) - 1):
        p1 = path.waypoints[i]
        p2 = path.waypoints[i + 1]
        gx1, gy1 = grid.world_to_grid(p1[0], p1[1])
        gx2, gy2 = grid.world_to_grid(p2[0], p2[1])
        # If moving diagonally, check neither touching cell is an obstacle
        if abs(gx2 - gx1) == 1 and abs(gy2 - gy1) == 1:
            assert not grid.is_grid_occupied(gx1, gy2)
            assert not grid.is_grid_occupied(gx2, gy1)


def test_astar_unreachable_or_colliding_start_goal() -> None:
    grid = OccupancyGridMap(min_x=0.0, min_y=0.0, max_x=10.0, max_y=10.0, resolution=0.5)
    grid.add_rectangular_obstacle(4.0, 4.0, 6.0, 6.0)

    planner = AStarPlanner(grid)

    # Start inside obstacle
    assert planner.plan(5.0, 5.0, 1.0, 1.0) is None

    # Goal inside obstacle
    assert planner.plan(1.0, 1.0, 5.0, 5.0) is None

    # Completely enclosed goal
    grid.add_rectangular_obstacle(0.0, 0.0, 3.0, 0.5)
    grid.add_rectangular_obstacle(0.0, 0.0, 0.5, 3.0)
    grid.add_rectangular_obstacle(2.5, 0.0, 3.0, 3.0)
    grid.add_rectangular_obstacle(0.0, 2.5, 3.0, 3.0)
    # (1.5, 1.5) is sealed
    assert planner.plan(8.0, 8.0, 1.5, 1.5) is None
