"""Pure Pursuit path tracking controller for differential-drive and mobile robots.

Inspired by PythonRobotics PathTracking formulations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from effero.skills.robotics.tracking.dwa import normalize_angle


@dataclass
class PurePursuitParams:
    """Configuration parameters for Pure Pursuit path tracker."""

    lookahead_gain: float = 0.2  # Lookahead distance velocity coefficient [s]
    min_lookahead_m: float = 0.35  # Minimum lookahead distance [m]
    max_lookahead_m: float = 1.5  # Maximum lookahead distance [m]
    target_speed_mps: float = 0.6  # Default cruising speed [m/s]
    max_angular_velocity: float = 1.2  # Max allowable turn rate [rad/s]
    goal_tolerance_m: float = 0.15  # Distance threshold to consider goal reached [m]


class PurePursuitController:
    """Geometric path tracking controller steering robot towards a dynamic lookahead point."""

    def __init__(self, params: PurePursuitParams | None = None) -> None:
        self.params = params or PurePursuitParams()

    def _calculate_lookahead_distance(self, current_speed: float) -> float:
        """Dynamically compute lookahead distance proportional to speed."""
        ld = self.params.lookahead_gain * abs(current_speed) + self.params.min_lookahead_m
        return min(max(ld, self.params.min_lookahead_m), self.params.max_lookahead_m)

    def _find_target_index(
        self,
        rx: float,
        ry: float,
        waypoints: list[tuple[float, float]],
        lookahead_dist: float,
    ) -> int:
        """Find the index of the waypoint ahead of robot at target lookahead distance."""
        if not waypoints:
            return 0

        # Step 1: Find closest waypoint to robot
        min_dist_sq = float("inf")
        closest_idx = 0
        for i, (wx, wy) in enumerate(waypoints):
            d_sq = (wx - rx) ** 2 + (wy - ry) ** 2
            if d_sq < min_dist_sq:
                min_dist_sq = d_sq
                closest_idx = i

        # Step 2: Search forward from closest index for lookahead point
        target_idx = closest_idx
        for i in range(closest_idx, len(waypoints)):
            wx, wy = waypoints[i]
            d = math.hypot(wx - rx, wy - ry)
            target_idx = i
            if d >= lookahead_dist:
                break

        return target_idx

    def compute_command(
        self,
        current_x: float,
        current_y: float,
        current_yaw: float,
        current_speed: float,
        waypoints: list[tuple[float, float]],
    ) -> dict[str, Any]:
        """Calculate target linear and angular velocity commands to follow waypoint path.

        Returns a dictionary with command velocities and tracking metrics.
        """
        if not waypoints:
            return {
                "linear_velocity": 0.0,
                "angular_velocity": 0.0,
                "goal_reached": True,
                "lookahead_distance": self.params.min_lookahead_m,
                "target_waypoint": None,
                "distance_to_goal": 0.0,
            }

        goal_x, goal_y = waypoints[-1]
        dist_to_goal = math.hypot(goal_x - current_x, goal_y - current_y)

        # Check if goal is reached
        if dist_to_goal <= self.params.goal_tolerance_m:
            return {
                "linear_velocity": 0.0,
                "angular_velocity": 0.0,
                "goal_reached": True,
                "lookahead_distance": self.params.min_lookahead_m,
                "target_waypoint": [goal_x, goal_y],
                "distance_to_goal": round(dist_to_goal, 3),
            }

        # Dynamic lookahead
        ld = self._calculate_lookahead_distance(current_speed)
        target_idx = self._find_target_index(current_x, current_y, waypoints, ld)
        tx, ty = waypoints[target_idx]

        # Heading error to lookahead target
        alpha = normalize_angle(math.atan2(ty - current_y, tx - current_x) - current_yaw)

        # Actual distance to chosen lookahead waypoint
        actual_ld = max(math.hypot(tx - current_x, ty - current_y), 0.05)

        # Smooth proportional deceleration when approaching final waypoint
        speed = self.params.target_speed_mps
        if dist_to_goal < 1.0:
            speed = max(self.params.target_speed_mps * (dist_to_goal / 1.0), 0.15)

        # Differential drive curvature: omega = (2 * v * sin(alpha)) / Ld
        omega = (2.0 * speed * math.sin(alpha)) / actual_ld
        omega = max(
            min(omega, self.params.max_angular_velocity),
            -self.params.max_angular_velocity,
        )

        return {
            "linear_velocity": round(speed, 3),
            "angular_velocity": round(omega, 3),
            "goal_reached": False,
            "lookahead_distance": round(actual_ld, 3),
            "target_waypoint": [round(tx, 3), round(ty, 3)],
            "target_index": target_idx,
            "distance_to_goal": round(dist_to_goal, 3),
        }
