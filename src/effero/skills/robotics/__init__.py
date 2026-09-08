"""Robotics Skills module."""

from __future__ import annotations

from effero.skills.robotics.arm import (
    ArmController,
    ArmKinematicModel,
    JointConfiguration,
    home,
    move_to,
    pick_place,
    set_gripper,
)
from effero.skills.robotics.collision import (
    ArmCollisionValidator,
    BoxObstacle,
    CylinderObstacle,
    Obstacle,
    SphereObstacle,
    WorkspaceBounds,
)
from effero.skills.robotics.grid_map import OccupancyGridMap
from effero.skills.robotics.navigate import get_position, go_to, go_to_coords, plan_path, stop
from effero.skills.robotics.planning.a_star import AStarPlanner, PlannedPath
from effero.skills.robotics.trajectory import (
    MinimumJerkTrajectory,
    MultiSegmentTrajectoryPlanner,
    QuinticPolynomial,
    TrajectoryPoint,
)

__all__ = [
    # Kinematics & Controllers
    "JointConfiguration",
    "ArmKinematicModel",
    "ArmController",
    # Trajectory Planning
    "TrajectoryPoint",
    "QuinticPolynomial",
    "MinimumJerkTrajectory",
    "MultiSegmentTrajectoryPlanner",
    # Collision & Obstacle Validation
    "WorkspaceBounds",
    "Obstacle",
    "BoxObstacle",
    "SphereObstacle",
    "CylinderObstacle",
    "ArmCollisionValidator",
    # Grid Mapping & Path Planning
    "OccupancyGridMap",
    "AStarPlanner",
    "PlannedPath",
    # Skills
    "move_to",
    "set_gripper",
    "pick_place",
    "home",
    "go_to",
    "go_to_coords",
    "stop",
    "get_position",
    "plan_path",
]
