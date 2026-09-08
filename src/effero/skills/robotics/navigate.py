"""Robot mobile base navigation, waypoint tracking, and differential drive kinematics."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

from effero.sdk.skill import SafetyClass, skill
from effero.skills.robotics.grid_map import OccupancyGridMap
from effero.skills.robotics.localization.ekf import (
    EKFLocalizer,
    Landmark,
    LandmarkObservation,
)
from effero.skills.robotics.planning.a_star import AStarPlanner
from effero.skills.robotics.tracking.dwa import DWAController, DWAParams, RobotState
from effero.skills.robotics.tracking.pure_pursuit import (
    PurePursuitController,
    PurePursuitParams,
)

logger = logging.getLogger(__name__)


@dataclass
class Pose2D:
    """2D planar pose of a mobile robot."""

    x: float = 0.0  # meters
    y: float = 0.0  # meters
    yaw: float = 0.0  # radians

    def to_dict(self) -> dict[str, float]:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "yaw_radians": round(self.yaw, 4),
            "yaw_degrees": round(math.degrees(self.yaw), 2),
        }


@dataclass
class Waypoint:
    """Named geographical coordinate in robot map frame."""

    name: str
    x: float
    y: float
    yaw_degrees: float = 0.0
    tolerance_meters: float = 0.05


class NavigationController:
    """Navigation engine tracking robot pose, waypoints, and differential kinematics."""

    def __init__(self) -> None:
        self.pose = Pose2D(0.0, 0.0, 0.0)
        self.linear_velocity_mps: float = 0.0
        self.angular_velocity_radps: float = 0.0
        self.max_linear_velocity: float = 0.8  # m/s
        self.max_angular_velocity: float = 1.2  # rad/s
        self.total_odometry_distance: float = 0.0
        self.emergency_stopped: bool = False

        # Preloaded reference map waypoints
        self.waypoints: dict[str, Waypoint] = {
            "charging_station": Waypoint("charging_station", 0.0, 0.0, 0.0),
            "kitchen": Waypoint("kitchen", 3.5, 1.2, 90.0),
            "living_room": Waypoint("living_room", 2.0, 4.0, 0.0),
            "office": Waypoint("office", -1.5, 3.0, 180.0),
            "lab": Waypoint("lab", 5.0, 5.0, 45.0),
        }

        # Grid map and A* path planner
        self.grid_map = OccupancyGridMap(min_x=-10.0, min_y=-10.0, max_x=10.0, max_y=10.0, resolution=0.1)
        self.robot_radius_m: float = 0.2
        self.planner = AStarPlanner(self.grid_map)

        # Path tracking and local obstacle avoidance
        self.dwa_controller = DWAController(DWAParams(robot_radius=self.robot_radius_m))
        self.pure_pursuit = PurePursuitController(PurePursuitParams())

        # Extended Kalman Filter localizer and spatial landmarks
        self.localizer = EKFLocalizer(
            initial_x=self.pose.x,
            initial_y=self.pose.y,
            initial_yaw=self.pose.yaw,
            initial_v=self.linear_velocity_mps,
        )
        self.landmarks: dict[str, Landmark] = {
            wp.name: Landmark(id=wp.name, x=wp.x, y=wp.y) for wp in self.waypoints.values()
        }

    def add_waypoint(self, name: str, x: float, y: float, yaw_deg: float = 0.0) -> None:
        """Register a new named coordinate in the map."""
        self.waypoints[name] = Waypoint(name=name, x=x, y=y, yaw_degrees=yaw_deg)
        self.landmarks[name] = Landmark(id=name, x=x, y=y)

    def navigate_to_coordinates(self, target_x: float, target_y: float, target_yaw_deg: float = 0.0) -> dict[str, Any]:
        """Plan and execute trajectory to Cartesian coordinates."""
        if self.emergency_stopped:
            return {
                "status": "error",
                "message": "Emergency stop is active. Clear stop before navigating.",
            }

        dx = target_x - self.pose.x
        dy = target_y - self.pose.y
        distance = math.hypot(dx, dy)
        target_yaw_rad = math.radians(target_yaw_deg)

        # Calculate transit trajectory parameters
        bearing = math.atan2(dy, dx) if distance > 1e-4 else self.pose.yaw
        turn_angle = abs(bearing - self.pose.yaw) % (2 * math.pi)
        if turn_angle > math.pi:
            turn_angle = 2 * math.pi - turn_angle

        # Time estimation based on trapezoidal velocity profiling
        transit_time = (distance / self.max_linear_velocity) + (turn_angle / self.max_angular_velocity)

        prev_pose = self.pose.to_dict()
        self.pose.x = target_x
        self.pose.y = target_y
        self.pose.yaw = target_yaw_rad
        self.total_odometry_distance += distance

        logger.info(
            f"Navigation complete: from ({prev_pose['x']}, {prev_pose['y']}) "
            f"to ({target_x}, {target_y}), distance: {distance:.2f}m, eta: {transit_time:.2f}s"
        )

        return {
            "status": "success",
            "distance_meters": round(distance, 3),
            "duration_seconds": round(transit_time, 2),
            "current_pose": self.pose.to_dict(),
            "odometry_total_meters": round(self.total_odometry_distance, 3),
        }

    def navigate_to_waypoint(self, name: str) -> dict[str, Any]:
        """Navigate to a registered waypoint by name."""
        if name not in self.waypoints:
            valid = list(self.waypoints.keys())
            return {
                "status": "error",
                "message": f"Waypoint '{name}' not found. Available: {valid}",
            }

        wp = self.waypoints[name]
        result = self.navigate_to_coordinates(wp.x, wp.y, wp.yaw_degrees)
        if result["status"] == "success":
            result["waypoint"] = name
        return result

    def stop(self) -> dict[str, Any]:
        """Trigger emergency stop and engage electromagnetic brakes."""
        self.linear_velocity_mps = 0.0
        self.angular_velocity_radps = 0.0
        self.emergency_stopped = True
        logger.warning("Mobile base EMERGENCY STOP engaged.")
        return {
            "status": "success",
            "action": "emergency_stop",
            "brakes_engaged": True,
            "pose": self.pose.to_dict(),
        }

    def clear_stop(self) -> dict[str, Any]:
        """Clear emergency stop state."""
        self.emergency_stopped = False
        logger.info("Mobile base emergency stop cleared.")
        return {"status": "success", "action": "clear_emergency_stop"}

    def set_grid_map(self, grid_map: OccupancyGridMap, robot_radius_m: float = 0.2) -> None:
        """Assign an active occupancy grid map and re-initialize the A* planner."""
        self.grid_map = grid_map
        self.robot_radius_m = robot_radius_m
        self.grid_map.inflate_obstacles(robot_radius_m)
        self.planner = AStarPlanner(self.grid_map)

    def plan_path_to(
        self,
        target_x: float,
        target_y: float,
        start_x: float | None = None,
        start_y: float | None = None,
        smooth: bool = True,
    ) -> dict[str, Any]:
        """Compute an obstacle-free trajectory to target using A* grid search."""
        sx = self.pose.x if start_x is None else start_x
        sy = self.pose.y if start_y is None else start_y

        path = self.planner.plan(sx, sy, target_x, target_y, smooth=smooth)
        if path is None:
            return {
                "status": "error",
                "message": "No collision-free path found to target coordinates.",
                "start": [round(sx, 3), round(sy, 3)],
                "target": [round(target_x, 3), round(target_y, 3)],
            }

        return {
            "status": "success",
            "start": [round(sx, 3), round(sy, 3)],
            "target": [round(target_x, 3), round(target_y, 3)],
            **path.to_dict(),
        }

    def compute_dwa_velocity(
        self,
        goal_x: float,
        goal_y: float,
        obstacles: list[tuple[float, float]] | None = None,
    ) -> dict[str, Any]:
        """Generate safe command velocities using DWA local obstacle avoidance."""
        obs = obstacles or []
        state = RobotState(
            x=self.pose.x,
            y=self.pose.y,
            yaw=self.pose.yaw,
            v=self.linear_velocity_mps,
            omega=self.angular_velocity_radps,
        )
        best_v, best_omega, traj = self.dwa_controller.compute_velocity(state, (goal_x, goal_y), obs)
        return {
            "linear_velocity": best_v,
            "angular_velocity": best_omega,
            "current_state": state.to_dict(),
            "goal": [goal_x, goal_y],
            "predicted_trajectory": traj,
        }

    def track_waypoints(
        self,
        waypoints: list[tuple[float, float]],
    ) -> dict[str, Any]:
        """Compute path tracking command using Pure Pursuit controller."""
        return self.pure_pursuit.compute_command(
            self.pose.x,
            self.pose.y,
            self.pose.yaw,
            self.linear_velocity_mps,
            waypoints,
        )

    def predict_step(self, control_v: float, control_omega: float, dt: float = 0.1) -> dict[str, Any]:
        """Advance robot state prediction using EKF kinematic motion model."""
        state = self.localizer.predict(control_v, control_omega, dt)
        self.pose.x = state.x
        self.pose.y = state.y
        self.pose.yaw = state.yaw
        self.linear_velocity_mps = state.v
        self.angular_velocity_radps = control_omega
        return {"status": "success", "state": state.to_dict()}

    def update_landmark_observation(self, landmark_id: str, range_m: float, bearing_rad: float) -> dict[str, Any]:
        """Update robot pose using a relative range/bearing measurement to a known landmark."""
        if landmark_id not in self.landmarks:
            return {
                "status": "error",
                "message": f"Landmark {landmark_id!r} not found in map.",
                "known_landmarks": list(self.landmarks.keys()),
            }

        landmark = self.landmarks[landmark_id]
        obs = LandmarkObservation(landmark_id=landmark_id, range_m=range_m, bearing_rad=bearing_rad)
        state = self.localizer.update_landmark(obs, landmark)
        self.pose.x = state.x
        self.pose.y = state.y
        self.pose.yaw = state.yaw
        return {"status": "success", "state": state.to_dict()}

    def update_position_fix(self, measured_x: float, measured_y: float, std_dev: float = 0.2) -> dict[str, Any]:
        """Fuse an absolute position coordinate fix into the robot state estimate."""
        state = self.localizer.update_position(measured_x, measured_y, measurement_std_dev=std_dev)
        self.pose.x = state.x
        self.pose.y = state.y
        self.pose.yaw = state.yaw
        return {"status": "success", "state": state.to_dict()}

    def get_telemetry(self) -> dict[str, Any]:
        """Read real-time navigation telemetry."""
        return {
            "status": "success",
            "pose": self.pose.to_dict(),
            "linear_velocity_mps": self.linear_velocity_mps,
            "angular_velocity_radps": self.angular_velocity_radps,
            "odometry_total_meters": round(self.total_odometry_distance, 3),
            "emergency_stopped": self.emergency_stopped,
            "registered_waypoints": list(self.waypoints.keys()),
            "grid_map": self.grid_map.to_dict(),
            "ekf_localization": self.localizer.get_state().to_dict(),
        }


#: Singleton navigation instance
_nav_controller = NavigationController()


@skill(
    name="robotics.navigate.go_to",
    description="Navigate mobile robot to a named map waypoint or Cartesian coordinates.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def go_to(waypoint: str) -> dict[str, Any]:
    return _nav_controller.navigate_to_waypoint(waypoint)


@skill(
    name="robotics.navigate.go_to_coords",
    description="Navigate robot base to exact (x, y, yaw_degrees) planar coordinates.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def go_to_coords(x: float, y: float, yaw_deg: float = 0.0) -> dict[str, Any]:
    return _nav_controller.navigate_to_coordinates(x, y, yaw_deg)


@skill(
    name="robotics.navigate.stop",
    description="Engage emergency brake and immediately halt all mobile base movement.",
    safety_class=SafetyClass.ACT_AUTONOMOUS,
)
async def stop() -> dict[str, Any]:
    return _nav_controller.stop()


@skill(
    name="robotics.navigate.get_position",
    description="Query current odometry pose, velocity, and distance telemetry.",
    safety_class=SafetyClass.READ_ONLY,
)
async def get_position() -> dict[str, Any]:
    return _nav_controller.get_telemetry()


@skill(
    name="robotics.navigate.plan_path",
    description="Compute collision-free 2D path waypoints to target coordinates using A* planning.",
    safety_class=SafetyClass.READ_ONLY,
)
async def plan_path(
    target_x: float,
    target_y: float,
    start_x: float | None = None,
    start_y: float | None = None,
    obstacles: list[dict[str, Any]] | None = None,
    robot_radius_m: float = 0.2,
    smooth: bool = True,
) -> dict[str, Any]:
    """Calculate an obstacle-free trajectory to target using A* grid planning."""
    if obstacles:
        grid = OccupancyGridMap(min_x=-15.0, min_y=-15.0, max_x=15.0, max_y=15.0, resolution=0.1)
        for obs in obstacles:
            obs_type = obs.get("type", "rectangle")
            if obs_type == "rectangle":
                grid.add_rectangular_obstacle(obs["min_x"], obs["min_y"], obs["max_x"], obs["max_y"])
            elif obs_type == "circle":
                grid.add_circular_obstacle(obs["x"], obs["y"], obs["radius"])
            elif obs_type == "line":
                grid.add_line_obstacle(obs["x0"], obs["y0"], obs["x1"], obs["y1"])

        grid.inflate_obstacles(robot_radius_m)
        planner = AStarPlanner(grid)
        sx = _nav_controller.pose.x if start_x is None else start_x
        sy = _nav_controller.pose.y if start_y is None else start_y
        res = planner.plan(sx, sy, target_x, target_y, smooth=smooth)
        if res is None:
            return {
                "status": "error",
                "message": "No collision-free path found to target coordinates.",
                "start": [round(sx, 3), round(sy, 3)],
                "target": [round(target_x, 3), round(target_y, 3)],
            }
        return {
            "status": "success",
            "start": [round(sx, 3), round(sy, 3)],
            "target": [round(target_x, 3), round(target_y, 3)],
            **res.to_dict(),
        }

    return _nav_controller.plan_path_to(target_x, target_y, start_x=start_x, start_y=start_y, smooth=smooth)


@skill(
    name="robotics.navigate.compute_velocity",
    description="Compute safe (linear, angular) velocity commands to reach a goal while avoiding obstacles via DWA.",
    safety_class=SafetyClass.READ_ONLY,
)
async def compute_velocity(
    goal_x: float,
    goal_y: float,
    obstacles: list[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Calculate instantaneous collision-free command velocities using Dynamic Window Approach."""
    return _nav_controller.compute_dwa_velocity(goal_x, goal_y, obstacles=obstacles)


@skill(
    name="robotics.navigate.track_path",
    description="Calculate steering and velocity commands to track waypoints using Pure Pursuit.",
    safety_class=SafetyClass.READ_ONLY,
)
async def track_path(
    waypoints: list[tuple[float, float]],
) -> dict[str, Any]:
    """Follow a planned trajectory of waypoints with lookahead steering."""
    return _nav_controller.track_waypoints(waypoints)


@skill(
    name="robotics.navigate.localize_predict",
    description="Advance robot state and covariance prediction using EKF motion model.",
    safety_class=SafetyClass.READ_ONLY,
)
async def localize_predict(
    control_v: float,
    control_omega: float,
    dt: float = 0.1,
) -> dict[str, Any]:
    """Propagate state and uncertainty forward in time given motion control inputs."""
    return _nav_controller.predict_step(control_v, control_omega, dt=dt)


@skill(
    name="robotics.navigate.localize_landmark",
    description="Fuse relative range and bearing measurement to a known landmark into EKF state.",
    safety_class=SafetyClass.READ_ONLY,
)
async def localize_landmark(
    landmark_id: str,
    range_m: float,
    bearing_rad: float,
) -> dict[str, Any]:
    """Correct robot state estimate using landmark observation."""
    return _nav_controller.update_landmark_observation(
        landmark_id=landmark_id, range_m=range_m, bearing_rad=bearing_rad
    )


@skill(
    name="robotics.navigate.localize_position_fix",
    description="Fuse an absolute coordinate position fix (GPS/UWB/vision) into EKF state.",
    safety_class=SafetyClass.READ_ONLY,
)
async def localize_position_fix(
    x: float,
    y: float,
    std_dev: float = 0.2,
) -> dict[str, Any]:
    """Correct robot state estimate using external coordinate measurement."""
    return _nav_controller.update_position_fix(x, y, std_dev=std_dev)
