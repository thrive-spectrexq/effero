"""A* 2D Grid Path Planner with diagonal corner-cutting prevention and line-of-sight smoothing."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Any

from effero.skills.robotics.grid_map import OccupancyGridMap


@dataclass
class PlannedPath:
    """Calculated 2D trajectory path with waypoints and metric distance."""

    waypoints: list[tuple[float, float]]
    total_distance_m: float
    expanded_nodes: int
    is_smoothed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "waypoints": self.waypoints,
            "total_distance_m": round(self.total_distance_m, 3),
            "waypoint_count": len(self.waypoints),
            "expanded_nodes": self.expanded_nodes,
            "is_smoothed": self.is_smoothed,
        }


class AStarPlanner:
    """Optimal 2D grid path planning using A* search with 8-connectivity and line-of-sight smoothing."""

    SQRT2: float = math.sqrt(2.0)

    # 8-connected transitions: (dx, dy, step_cost)
    MOTIONS: list[tuple[int, int, float]] = [
        (1, 0, 1.0),
        (-1, 0, 1.0),
        (0, 1, 1.0),
        (0, -1, 1.0),
        (1, 1, SQRT2),
        (1, -1, SQRT2),
        (-1, 1, SQRT2),
        (-1, -1, SQRT2),
    ]

    def __init__(self, grid_map: OccupancyGridMap) -> None:
        self.grid_map = grid_map

    def _heuristic(self, gx: int, gy: int, target_gx: int, target_gy: int) -> float:
        """Octile distance heuristic for 8-connected grid search."""
        dx = abs(gx - target_gx)
        dy = abs(gy - target_gy)
        return (max(dx, dy) + (self.SQRT2 - 1.0) * min(dx, dy)) * self.grid_map.resolution

    def plan(
        self,
        start_x: float,
        start_y: float,
        goal_x: float,
        goal_y: float,
        smooth: bool = True,
        include_inflated: bool = True,
    ) -> PlannedPath | None:
        """Find optimal collision-free path from start coordinates to goal coordinates.

        Returns None if start or goal is in collision or no obstacle-free path exists.
        """
        start_gx, start_gy = self.grid_map.world_to_grid(start_x, start_y)
        goal_gx, goal_gy = self.grid_map.world_to_grid(goal_x, goal_y)

        # Pre-flight boundary and obstacle check
        if not self.grid_map.in_bounds(start_gx, start_gy):
            return None
        if not self.grid_map.in_bounds(goal_gx, goal_gy):
            return None
        if self.grid_map.is_grid_occupied(start_gx, start_gy, include_inflated=include_inflated):
            return None
        if self.grid_map.is_grid_occupied(goal_gx, goal_gy, include_inflated=include_inflated):
            return None

        # Trivial path
        if (start_gx, start_gy) == (goal_gx, goal_gy):
            return PlannedPath(
                waypoints=[(start_x, start_y), (goal_x, goal_y)],
                total_distance_m=math.hypot(goal_x - start_x, goal_y - start_y),
                expanded_nodes=0,
                is_smoothed=smooth,
            )

        # Priority queue entries: (f_score, counter, gx, gy)
        counter = 0
        open_set: list[tuple[float, int, int, int]] = []
        start_h = self._heuristic(start_gx, start_gy, goal_gx, goal_gy)
        heapq.heappush(open_set, (start_h, counter, start_gx, start_gy))

        # Costs and predecessors
        g_scores: dict[tuple[int, int], float] = {(start_gx, start_gy): 0.0}
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        closed_set: set[tuple[int, int]] = set()

        goal_reached = False
        expanded_nodes = 0

        while open_set:
            _, _, curr_gx, curr_gy = heapq.heappop(open_set)
            curr = (curr_gx, curr_gy)

            if curr in closed_set:
                continue
            closed_set.add(curr)
            expanded_nodes += 1

            if curr == (goal_gx, goal_gy):
                goal_reached = True
                break

            curr_g = g_scores[curr]

            for dx, dy, motion_cost in self.MOTIONS:
                nbr_gx = curr_gx + dx
                nbr_gy = curr_gy + dy
                nbr = (nbr_gx, nbr_gy)

                if not self.grid_map.in_bounds(nbr_gx, nbr_gy):
                    continue
                if self.grid_map.is_grid_occupied(nbr_gx, nbr_gy, include_inflated=include_inflated):
                    continue

                # Prevent diagonal corner-cutting through touching obstacles
                if dx != 0 and dy != 0:
                    if self.grid_map.is_grid_occupied(
                        curr_gx + dx, curr_gy, include_inflated=include_inflated
                    ) or self.grid_map.is_grid_occupied(curr_gx, curr_gy + dy, include_inflated=include_inflated):
                        continue

                tentative_g = curr_g + (motion_cost * self.grid_map.resolution)
                if tentative_g < g_scores.get(nbr, float("inf")):
                    g_scores[nbr] = tentative_g
                    came_from[nbr] = curr
                    f_score = tentative_g + self._heuristic(nbr_gx, nbr_gy, goal_gx, goal_gy)
                    counter += 1
                    heapq.heappush(open_set, (f_score, counter, nbr_gx, nbr_gy))

        if not goal_reached:
            return None

        # Reconstruct path from goal back to start
        curr_step = (goal_gx, goal_gy)
        grid_path: list[tuple[int, int]] = [curr_step]
        while curr_step in came_from:
            curr_step = came_from[curr_step]
            grid_path.append(curr_step)
        grid_path.reverse()

        # Convert grid indices to continuous world coordinates
        raw_waypoints: list[tuple[float, float]] = []
        raw_waypoints.append((start_x, start_y))
        for gx, gy in grid_path[1:-1]:
            raw_waypoints.append(self.grid_map.grid_to_world(gx, gy))
        raw_waypoints.append((goal_x, goal_y))

        final_waypoints = self._smooth_path(raw_waypoints) if smooth else raw_waypoints

        total_distance = self._calculate_path_distance(final_waypoints)

        return PlannedPath(
            waypoints=final_waypoints,
            total_distance_m=total_distance,
            expanded_nodes=expanded_nodes,
            is_smoothed=smooth,
        )

    def _smooth_path(self, waypoints: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """Short-cut intermediate grid waypoints with direct line-of-sight ray-casting."""
        if len(waypoints) <= 2:
            return waypoints

        smoothed: list[tuple[float, float]] = [waypoints[0]]
        curr_idx = 0

        while curr_idx < len(waypoints) - 1:
            furthest_idx = len(waypoints) - 1
            while furthest_idx > curr_idx + 1:
                p0 = smoothed[-1]
                p1 = waypoints[furthest_idx]
                if self.grid_map.is_line_clear(p0[0], p0[1], p1[0], p1[1]):
                    break
                furthest_idx -= 1

            smoothed.append(waypoints[furthest_idx])
            curr_idx = furthest_idx

        return smoothed

    @staticmethod
    def _calculate_path_distance(waypoints: list[tuple[float, float]]) -> float:
        dist = 0.0
        for i in range(len(waypoints) - 1):
            dist += math.hypot(
                waypoints[i + 1][0] - waypoints[i][0],
                waypoints[i + 1][1] - waypoints[i][1],
            )
        return dist
