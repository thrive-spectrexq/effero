"""Robotics arm motion planning and kinematics execution skills."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from effero.sdk.skill import SafetyClass, skill

logger = logging.getLogger(__name__)


@dataclass
class JointConfiguration:
    """Robot arm joint angles in radians."""

    base: float = 0.0      # q1 (yaw)
    shoulder: float = 0.0  # q2 (pitch)
    elbow: float = 0.0     # q3 (pitch)
    wrist: float = 0.0     # q4 (pitch)

    def to_degrees(self) -> dict[str, float]:
        return {
            "base": math.degrees(self.base),
            "shoulder": math.degrees(self.shoulder),
            "elbow": math.degrees(self.elbow),
            "wrist": math.degrees(self.wrist),
        }


@dataclass
class ArmKinematicModel:
    """Analytical kinematic model for a serial articulated robot arm."""

    # Link lengths in meters (default: 0.15m base height, 0.25m upper arm, 0.22m forearm, 0.08m end-effector)
    l0: float = 0.15
    l1: float = 0.25
    l2: float = 0.22
    l3: float = 0.08

    max_reach: float = 0.55
    min_reach: float = 0.10

    def forward_kinematics(self, joints: JointConfiguration) -> tuple[float, float, float]:
        """Compute end-effector Cartesian coordinates (x, y, z) from joint angles."""
        r = (
            self.l1 * math.cos(joints.shoulder)
            + self.l2 * math.cos(joints.shoulder + joints.elbow)
            + self.l3 * math.cos(joints.shoulder + joints.elbow + joints.wrist)
        )
        x = r * math.cos(joints.base)
        y = r * math.sin(joints.base)
        z = (
            self.l0
            + self.l1 * math.sin(joints.shoulder)
            + self.l2 * math.sin(joints.shoulder + joints.elbow)
            + self.l3 * math.sin(joints.shoulder + joints.elbow + joints.wrist)
        )
        return (round(x, 4), round(y, 4), round(z, 4))

    def inverse_kinematics(
        self,
        target_x: float,
        target_y: float,
        target_z: float,
        pitch_approach: float = 0.0,
    ) -> JointConfiguration:
        """Analytical inverse kinematics solving joint angles from Cartesian coordinates."""
        dist_xy = math.hypot(target_x, target_y)
        dist_3d = math.sqrt(target_x**2 + target_y**2 + (target_z - self.l0) ** 2)

        if dist_3d > self.max_reach:
            raise ValueError(
                f"Target position ({target_x}, {target_y}, {target_z}) exceeds maximum reach ({self.max_reach:.2f}m)"
            )
        if dist_3d < self.min_reach:
            raise ValueError(
                f"Target position ({target_x}, {target_y}, {target_z}) within minimum singularity zone ({self.min_reach:.2f}m)"
            )

        # Base angle (yaw)
        q1 = math.atan2(target_y, target_x)

        # Wrist position
        wx = dist_xy - self.l3 * math.cos(pitch_approach)
        wz = (target_z - self.l0) - self.l3 * math.sin(pitch_approach)

        d = math.hypot(wx, wz)
        cos_q3 = (d**2 - self.l1**2 - self.l2**2) / (2 * self.l1 * self.l2)
        cos_q3 = max(-1.0, min(1.0, cos_q3))
        # Elbow-up configuration
        q3 = -math.acos(cos_q3)

        alpha = math.atan2(wz, wx)
        beta = math.atan2(self.l2 * math.sin(-q3), self.l1 + self.l2 * math.cos(-q3))
        q2 = alpha + beta

        # Wrist orientation
        q4 = pitch_approach - (q2 + q3)

        return JointConfiguration(base=q1, shoulder=q2, elbow=q3, wrist=q4)


class ArmController:
    """Stateful arm controller managing trajectory planning, execution, and gripper state."""

    def __init__(self, model: ArmKinematicModel | None = None):
        self.model = model or ArmKinematicModel()
        self.current_joints = JointConfiguration()
        self.gripper_open = True
        self.velocity_limit_rad_s = 1.5

    @property
    def current_position(self) -> tuple[float, float, float]:
        return self.model.forward_kinematics(self.current_joints)

    def move_to_cartesian(
        self, x: float, y: float, z: float, pitch: float = 0.0
    ) -> dict[str, Any]:
        """Plan and execute joint trajectory to Cartesian target."""
        target_joints = self.model.inverse_kinematics(x, y, z, pitch)

        # Calculate joint displacement and duration based on velocity limits
        deltas = [
            abs(target_joints.base - self.current_joints.base),
            abs(target_joints.shoulder - self.current_joints.shoulder),
            abs(target_joints.elbow - self.current_joints.elbow),
            abs(target_joints.wrist - self.current_joints.wrist),
        ]
        max_delta = max(deltas)
        duration = max(0.2, max_delta / self.velocity_limit_rad_s)

        prev_pos = self.current_position
        self.current_joints = target_joints
        new_pos = self.current_position

        logger.info(
            f"Arm moved from {prev_pos} to {new_pos} (duration: {duration:.2f}s)"
        )
        return {
            "status": "success",
            "position": {"x": new_pos[0], "y": new_pos[1], "z": new_pos[2]},
            "joints_degrees": target_joints.to_degrees(),
            "trajectory_duration_seconds": round(duration, 3),
            "gripper_open": self.gripper_open,
        }

    def set_gripper(self, open_gripper: bool) -> dict[str, Any]:
        """Actuate gripper mechanism."""
        self.gripper_open = open_gripper
        logger.info(f"Gripper set to: {'OPEN' if open_gripper else 'CLOSED'}")
        return {
            "status": "success",
            "gripper_state": "open" if open_gripper else "closed",
        }

    def home(self) -> dict[str, Any]:
        """Return all joints to calibrated zero home position."""
        self.current_joints = JointConfiguration(0.0, 0.0, 0.0, 0.0)
        self.gripper_open = True
        pos = self.current_position
        return {
            "status": "success",
            "state": "homed",
            "position": {"x": pos[0], "y": pos[1], "z": pos[2]},
            "joints_degrees": self.current_joints.to_degrees(),
        }


#: Singleton controller instance
_arm_controller = ArmController()


@skill(
    name="robotics.arm.move_to",
    description="Calculate kinematics and move robot arm end-effector to target Cartesian position (x, y, z).",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def move_to(x: float, y: float, z: float, pitch: float = 0.0) -> dict[str, Any]:
    return _arm_controller.move_to_cartesian(x, y, z, pitch)


@skill(
    name="robotics.arm.set_gripper",
    description="Actuate arm gripper mechanism to grab or release objects.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def set_gripper(open_gripper: bool) -> dict[str, Any]:
    return _arm_controller.set_gripper(open_gripper)


@skill(
    name="robotics.arm.pick_place",
    description="Execute complete autonomous pick-and-place sequence with approach, grasp, transfer, and release.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def pick_place(
    pick_x: float,
    pick_y: float,
    pick_z: float,
    place_x: float,
    place_y: float,
    place_z: float,
    clearance_height: float = 0.10,
) -> dict[str, Any]:
    """Multi-stage pick and place trajectory sequence."""
    steps = []

    # 1. Open gripper
    steps.append(_arm_controller.set_gripper(open_gripper=True))

    # 2. Move to pre-pick clearance
    steps.append(_arm_controller.move_to_cartesian(pick_x, pick_y, pick_z + clearance_height))

    # 3. Descend to pick
    steps.append(_arm_controller.move_to_cartesian(pick_x, pick_y, pick_z))

    # 4. Grasp
    steps.append(_arm_controller.set_gripper(open_gripper=False))

    # 5. Lift to clearance
    steps.append(_arm_controller.move_to_cartesian(pick_x, pick_y, pick_z + clearance_height))

    # 6. Transit to pre-place clearance
    steps.append(_arm_controller.move_to_cartesian(place_x, place_y, place_z + clearance_height))

    # 7. Descend to place
    steps.append(_arm_controller.move_to_cartesian(place_x, place_y, place_z))

    # 8. Release
    steps.append(_arm_controller.set_gripper(open_gripper=True))

    # 9. Retract
    steps.append(_arm_controller.move_to_cartesian(place_x, place_y, place_z + clearance_height))

    return {
        "status": "success",
        "action": "pick_place",
        "pick_target": [pick_x, pick_y, pick_z],
        "place_target": [place_x, place_y, place_z],
        "stages_executed": len(steps),
        "final_position": _arm_controller.current_position,
    }


@skill(
    name="robotics.arm.home",
    description="Return arm to default home configuration.",
    safety_class=SafetyClass.ACT_AUTONOMOUS,
)
async def home() -> dict[str, Any]:
    return _arm_controller.home()
