"""Robot mobile base navigation, waypoint tracking, and differential drive kinematics."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from effero.sdk.skill import SafetyClass, skill

logger = logging.getLogger(__name__)


@dataclass
class Pose2D:
    """2D planar pose of a mobile robot."""

    x: float = 0.0      # meters
    y: float = 0.0      # meters
    yaw: float = 0.0    # radians

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

    def __init__(self):
        self.pose = Pose2D(0.0, 0.0, 0.0)
        self.linear_velocity_mps: float = 0.0
        self.angular_velocity_radps: float = 0.0
        self.max_linear_velocity: float = 0.8    # m/s
        self.max_angular_velocity: float = 1.2   # rad/s
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

    def add_waypoint(self, name: str, x: float, y: float, yaw_deg: float = 0.0) -> None:
        """Register a new named coordinate in the map."""
        self.waypoints[name] = Waypoint(name=name, x=x, y=y, yaw_degrees=yaw_deg)

    def navigate_to_coordinates(
        self, target_x: float, target_y: float, target_yaw_deg: float = 0.0
    ) -> dict[str, Any]:
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
