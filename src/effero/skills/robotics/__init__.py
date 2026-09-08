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
from effero.skills.robotics.localization.ekf import (
    EKFLocalizer,
    EKFState,
    Landmark,
    LandmarkObservation,
)
from effero.skills.robotics.navigate import (
    compute_velocity,
    get_position,
    go_to,
    go_to_coords,
    localize_landmark,
    localize_position_fix,
    localize_predict,
    plan_path,
    stop,
    track_path,
)
from effero.skills.robotics.planning.a_star import AStarPlanner, PlannedPath
from effero.skills.robotics.tracking.dwa import DWAController, DWAParams, RobotState
from effero.skills.robotics.tracking.pure_pursuit import (
    PurePursuitController,
    PurePursuitParams,
)
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
    # Path Tracking & Dynamic Obstacle Avoidance
    "RobotState",
    "DWAParams",
    "DWAController",
    "PurePursuitParams",
    "PurePursuitController",
    # Localization & State Estimation
    "EKFState",
    "Landmark",
    "LandmarkObservation",
    "EKFLocalizer",
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
    "compute_velocity",
    "track_path",
    "localize_predict",
    "localize_landmark",
    "localize_position_fix",
]
