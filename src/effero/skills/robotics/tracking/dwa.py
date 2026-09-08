"""Dynamic Window Approach (DWA) local obstacle avoidance and trajectory generation.

Inspired by PythonRobotics and the foundational DWA formulation (Fox et al., 1997).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class DWAParams:
    """Kinodynamic and scoring parameters for Dynamic Window Approach."""

    max_speed: float = 1.0  # [m/s]
    min_speed: float = -0.1  # [m/s]
    max_yaw_rate: float = math.radians(90.0)  # [rad/s]
    max_accel: float = 0.8  # [m/s^2]
    max_delta_yaw_rate: float = math.radians(120.0)  # [rad/s^2]
    v_resolution: float = 0.05  # [m/s]
    yaw_rate_resolution: float = math.radians(3.0)  # [rad/s]
    dt: float = 0.1  # [s] time step
    predict_time: float = 2.0  # [s] trajectory prediction horizon
    to_goal_cost_gain: float = 0.15
    speed_cost_gain: float = 1.0
    obstacle_cost_gain: float = 1.2
    robot_radius: float = 0.25  # [m]


@dataclass
class RobotState:
    """Planar kinematic state of a differential-drive robot."""

    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0  # [rad]
    v: float = 0.0  # [m/s]
    omega: float = 0.0  # [rad/s]

    def to_dict(self) -> dict[str, float]:
        return {
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "yaw": round(self.yaw, 3),
            "v": round(self.v, 3),
            "omega": round(self.omega, 3),
        }


def normalize_angle(angle: float) -> float:
    """Normalize angle to [-pi, pi]."""
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


class DWAController:
    """Real-time local obstacle avoidance selecting optimal (v, omega) within dynamic limits."""

    def __init__(self, params: DWAParams | None = None) -> None:
        self.params = params or DWAParams()

    def _motion_model(
        self, state: tuple[float, float, float, float, float], v: float, omega: float, dt: float
    ) -> tuple[float, float, float, float, float]:
        """Integrate differential-drive forward kinematics for duration dt."""
        x, y, yaw, _, _ = state
        yaw_new = yaw + omega * dt
        x_new = x + v * math.cos(yaw_new) * dt
        y_new = y + v * math.sin(yaw_new) * dt
        return x_new, y_new, yaw_new, v, omega

    def _calculate_dynamic_window(self, current_v: float, current_omega: float) -> tuple[float, float, float, float]:
        """Compute permissible [min_v, max_v, min_omega, max_omega] window."""
        # Hardware limits
        vs = [
            self.params.min_speed,
            self.params.max_speed,
            -self.params.max_yaw_rate,
            self.params.max_yaw_rate,
        ]

        # Acceleration-constrained dynamic limits
        vd = [
            current_v - self.params.max_accel * self.params.dt,
            current_v + self.params.max_accel * self.params.dt,
            current_omega - self.params.max_delta_yaw_rate * self.params.dt,
            current_omega + self.params.max_delta_yaw_rate * self.params.dt,
        ]

        return (
            max(vs[0], vd[0]),
            min(vs[1], vd[1]),
            max(vs[2], vd[2]),
            min(vs[3], vd[3]),
        )

    def _predict_trajectory(self, initial_state: RobotState, v: float, omega: float) -> list[tuple[float, float]]:
        """Simulate robot Cartesian coordinates over the prediction horizon."""
        state = (
            initial_state.x,
            initial_state.y,
            initial_state.yaw,
            initial_state.v,
            initial_state.omega,
        )
        trajectory: list[tuple[float, float]] = [(state[0], state[1])]
        time_elapsed = 0.0

        while time_elapsed <= self.params.predict_time:
            state = self._motion_model(state, v, omega, self.params.dt)
            trajectory.append((state[0], state[1]))
            time_elapsed += self.params.dt

        return trajectory

    def _calculate_obstacle_cost(
        self,
        trajectory: list[tuple[float, float]],
        obstacles: list[tuple[float, float]],
    ) -> float:
        """Compute obstacle distance penalty; returns infinity if collision occurs."""
        if not obstacles:
            return 0.0

        min_dist = float("inf")
        r_sq = self.params.robot_radius**2

        for px, py in trajectory:
            for ox, oy in obstacles:
                dx = px - ox
                dy = py - oy
                dist_sq = dx * dx + dy * dy
                if dist_sq <= r_sq:
                    return float("inf")  # Immediate collision along path
                if dist_sq < min_dist:
                    min_dist = dist_sq

        actual_min_dist = math.sqrt(min_dist)
        # Higher cost when closer to obstacle boundary
        return 1.0 / max(actual_min_dist - self.params.robot_radius, 0.01)

    def _calculate_to_goal_cost(
        self,
        trajectory: list[tuple[float, float]],
        goal: tuple[float, float],
        final_yaw: float,
    ) -> float:
        """Score alignment of robot trajectory towards target goal."""
        end_x, end_y = trajectory[-1]
        dx = goal[0] - end_x
        dy = goal[1] - end_y
        error_angle = math.atan2(dy, dx) - final_yaw
        return abs(normalize_angle(error_angle))

    def compute_velocity(
        self,
        state: RobotState,
        goal: tuple[float, float],
        obstacles: list[tuple[float, float]],
    ) -> tuple[float, float, list[tuple[float, float]]]:
        """Evaluate reachable (v, omega) pairs and return the optimal command velocity."""
        min_v, max_v, min_omega, max_omega = self._calculate_dynamic_window(state.v, state.omega)

        best_cost = float("inf")
        best_v = 0.0
        best_omega = 0.0
        best_trajectory: list[tuple[float, float]] = [(state.x, state.y)]

        # If already at goal within tolerance, stop
        dist_to_goal = math.hypot(goal[0] - state.x, goal[1] - state.y)
        if dist_to_goal < 0.15:
            return 0.0, 0.0, [(state.x, state.y)]

        v = min_v
        while v <= max_v + 1e-5:
            omega = min_omega
            while omega <= max_omega + 1e-5:
                traj = self._predict_trajectory(state, v, omega)

                # Final predicted heading
                final_yaw = state.yaw + omega * self.params.predict_time

                to_goal_cost = self.params.to_goal_cost_gain * self._calculate_to_goal_cost(traj, goal, final_yaw)
                speed_cost = self.params.speed_cost_gain * (self.params.max_speed - v)
                ob_cost = self.params.obstacle_cost_gain * self._calculate_obstacle_cost(traj, obstacles)

                total_cost = to_goal_cost + speed_cost + ob_cost

                if total_cost < best_cost:
                    best_cost = total_cost
                    best_v = v
                    best_omega = omega
                    best_trajectory = traj

                omega += self.params.yaw_rate_resolution
            v += self.params.v_resolution

        # If all candidates collide, emergency stop
        if math.isinf(best_cost):
            return 0.0, 0.0, [(state.x, state.y)]

        return round(best_v, 3), round(best_omega, 3), best_trajectory
