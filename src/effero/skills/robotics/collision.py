"""Cartesian workspace collision boundary validation and geometric obstacle checking."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from effero.skills.robotics.arm import JointConfiguration
    from effero.skills.robotics.trajectory import TrajectoryPoint


@dataclass
class WorkspaceBounds:
    """Cartesian 3D workspace bounding limits and minimum table clearance."""

    min_x: float = -0.60
    max_x: float = 0.60
    min_y: float = -0.60
    max_y: float = 0.60
    min_z: float = 0.0
    max_z: float = 0.70
    min_table_z: float = 0.0  # Absolute tabletop plane height

    def contains_point(self, point: tuple[float, float, float], clearance: float = 0.0) -> bool:
        """Check if 3D point is within safe bounds with specified clearance."""
        x, y, z = point
        if not (self.min_x + clearance <= x <= self.max_x - clearance):
            return False
        if not (self.min_y + clearance <= y <= self.max_y - clearance):
            return False
        if not (self.min_z + clearance <= z <= self.max_z - clearance):
            return False
        if z < self.min_table_z + clearance:
            return False
        return True


class Obstacle(ABC):
    """Abstract geometric obstacle primitive."""

    @abstractmethod
    def signed_distance_point(self, p: tuple[float, float, float]) -> float:
        """Compute signed distance to point p: negative inside, 0 on boundary, positive outside."""
        ...

    def contains_point(self, p: tuple[float, float, float], margin: float = 0.0) -> bool:
        """Return True if point is inside obstacle or within margin."""
        return self.signed_distance_point(p) <= margin

    def distance_to_segment(
        self,
        p1: tuple[float, float, float],
        p2: tuple[float, float, float],
        samples: int = 15,
    ) -> float:
        """Compute minimum signed distance from line segment [p1, p2] to the obstacle."""
        min_dist = float("inf")
        for i in range(samples + 1):
            t = i / float(samples)
            px = p1[0] + t * (p2[0] - p1[0])
            py = p1[1] + t * (p2[1] - p1[1])
            pz = p1[2] + t * (p2[2] - p1[2])
            dist = self.signed_distance_point((px, py, pz))
            if dist < min_dist:
                min_dist = dist
        return min_dist


class SphereObstacle(Obstacle):
    """3D spherical obstacle defined by center and radius."""

    def __init__(self, center: tuple[float, float, float], radius: float) -> None:
        if radius <= 0:
            raise ValueError(f"Sphere radius must be positive, got {radius}")
        self.center = center
        self.radius = radius

    def signed_distance_point(self, p: tuple[float, float, float]) -> float:
        cx, cy, cz = self.center
        dx = p[0] - cx
        dy = p[1] - cy
        dz = p[2] - cz
        dist_to_center = math.sqrt(dx * dx + dy * dy + dz * dz)
        return dist_to_center - self.radius

    def distance_to_segment(
        self,
        p1: tuple[float, float, float],
        p2: tuple[float, float, float],
        samples: int = 15,
    ) -> float:
        # Analytical distance from segment p1->p2 to sphere center
        cx, cy, cz = self.center
        vx = p2[0] - p1[0]
        vy = p2[1] - p1[1]
        vz = p2[2] - p1[2]
        seg_len_sq = vx * vx + vy * vy + vz * vz

        if seg_len_sq < 1e-12:
            return self.signed_distance_point(p1)

        # Projection factor t
        t = ((cx - p1[0]) * vx + (cy - p1[1]) * vy + (cz - p1[2]) * vz) / seg_len_sq
        t_clamped = max(0.0, min(1.0, t))
        closest_x = p1[0] + t_clamped * vx
        closest_y = p1[1] + t_clamped * vy
        closest_z = p1[2] + t_clamped * vz

        dist_to_center = math.sqrt((closest_x - cx) ** 2 + (closest_y - cy) ** 2 + (closest_z - cz) ** 2)
        return dist_to_center - self.radius


class BoxObstacle(Obstacle):
    """Axis-Aligned 3D Bounding Box (AABB) obstacle centered at center with dimensions size."""

    def __init__(
        self,
        center: tuple[float, float, float],
        size: tuple[float, float, float],
    ) -> None:
        if any(s <= 0 for s in size):
            raise ValueError(f"Box dimensions must be positive, got {size}")
        self.center = center
        self.size = size
        self.half_size = (size[0] / 2.0, size[1] / 2.0, size[2] / 2.0)

    def signed_distance_point(self, p: tuple[float, float, float]) -> float:
        cx, cy, cz = self.center
        hx, hy, hz = self.half_size

        dx = abs(p[0] - cx) - hx
        dy = abs(p[1] - cy) - hy
        dz = abs(p[2] - cz) - hz

        outside_x = max(0.0, dx)
        outside_y = max(0.0, dy)
        outside_z = max(0.0, dz)
        outside_dist = math.sqrt(outside_x**2 + outside_y**2 + outside_z**2)

        inside_dist = min(0.0, max(dx, dy, dz))
        return outside_dist + inside_dist


class CylinderObstacle(Obstacle):
    """Vertical cylinder obstacle aligned along Z axis with center, radius, and height."""

    def __init__(
        self,
        center: tuple[float, float, float],
        radius: float,
        height: float,
    ) -> None:
        if radius <= 0 or height <= 0:
            raise ValueError(f"Radius and height must be positive, got r={radius}, h={height}")
        self.center = center
        self.radius = radius
        self.height = height
        self.half_height = height / 2.0

    def signed_distance_point(self, p: tuple[float, float, float]) -> float:
        cx, cy, cz = self.center
        dx = p[0] - cx
        dy = p[1] - cy
        r_dist = math.sqrt(dx * dx + dy * dy) - self.radius
        z_dist = abs(p[2] - cz) - self.half_height

        outside_r = max(0.0, r_dist)
        outside_z = max(0.0, z_dist)
        outside_dist = math.sqrt(outside_r**2 + outside_z**2)

        inside_dist = min(0.0, max(r_dist, z_dist))
        return outside_dist + inside_dist


class ArmCollisionValidator:
    """Validates robot arm configurations and trajectories against workspace bounds and obstacles.

    Models the serial robot arm links as capsules of radius link_radius.
    """

    def __init__(
        self,
        l0: float = 0.15,
        l1: float = 0.25,
        l2: float = 0.22,
        l3: float = 0.08,
        link_radius: float = 0.03,
        workspace: WorkspaceBounds | None = None,
    ) -> None:
        self.l0 = l0
        self.l1 = l1
        self.l2 = l2
        self.l3 = l3
        self.link_radius = link_radius
        self.workspace = workspace or WorkspaceBounds()
        self.obstacles: list[Obstacle] = []

    def add_obstacle(self, obstacle: Obstacle) -> None:
        """Add an obstacle primitive to collision environment."""
        self.obstacles.append(obstacle)

    def remove_obstacle(self, obstacle: Obstacle) -> None:
        """Remove an obstacle primitive."""
        if obstacle in self.obstacles:
            self.obstacles.remove(obstacle)

    def clear_obstacles(self) -> None:
        """Clear all obstacle primitives."""
        self.obstacles.clear()

    def get_joint_positions(
        self,
        joints: JointConfiguration | list[float],
    ) -> list[tuple[float, float, float]]:
        """Compute 3D Cartesian coordinates of all arm keypoints P0, P1, P2, P3, P4.

        P0: Base origin (0, 0, 0)
        P1: Base turret top / shoulder joint (0, 0, l0)
        P2: Elbow joint
        P3: Wrist joint
        P4: End-effector tip
        """
        if isinstance(joints, list):
            q1, q2, q3, q4 = joints[0], joints[1], joints[2], joints[3]
        else:
            q1, q2, q3, q4 = joints.base, joints.shoulder, joints.elbow, joints.wrist

        p0 = (0.0, 0.0, 0.0)
        p1 = (0.0, 0.0, self.l0)

        r2 = self.l1 * math.cos(q2)
        p2 = (
            r2 * math.cos(q1),
            r2 * math.sin(q1),
            self.l0 + self.l1 * math.sin(q2),
        )

        r3 = self.l1 * math.cos(q2) + self.l2 * math.cos(q2 + q3)
        p3 = (
            r3 * math.cos(q1),
            r3 * math.sin(q1),
            self.l0 + self.l1 * math.sin(q2) + self.l2 * math.sin(q2 + q3),
        )

        r4 = r3 + self.l3 * math.cos(q2 + q3 + q4)
        p4 = (
            r4 * math.cos(q1),
            r4 * math.sin(q1),
            self.l0 + self.l1 * math.sin(q2) + self.l2 * math.sin(q2 + q3) + self.l3 * math.sin(q2 + q3 + q4),
        )

        return [p0, p1, p2, p3, p4]

    def get_link_segments(
        self,
        joints: JointConfiguration | list[float],
    ) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
        """Compute the line segments for all arm links."""
        pts = self.get_joint_positions(joints)
        return [
            (pts[0], pts[1]),  # Base link
            (pts[1], pts[2]),  # Upper arm link
            (pts[2], pts[3]),  # Forearm link
            (pts[3], pts[4]),  # Wrist/end-effector link
        ]

    def validate_configuration(
        self,
        joints: JointConfiguration | list[float],
    ) -> tuple[bool, str | None]:
        """Validate an individual joint configuration against workspace bounds and obstacles.

        Returns:
            (True, None) if safe.
            (False, "description of violation") if in collision.
        """
        pts = self.get_joint_positions(joints)
        segments = self.get_link_segments(joints)

        # 1. Check workspace boundaries and table clearance
        # P0 is base origin on table, so check links from P1 onwards
        for i, pt in enumerate(pts[1:], start=1):
            if not self.workspace.contains_point(pt, clearance=-self.link_radius):
                return (
                    False,
                    f"Joint/link point P{i} ({pt[0]:.3f}, {pt[1]:.3f}, {pt[2]:.3f}) violates workspace bounds",
                )

        # Check lowest point on each moving link segment against table clearance
        for idx, (p_start, p_end) in enumerate(segments[1:], start=1):
            min_z_seg = min(p_start[2], p_end[2]) - self.link_radius
            if min_z_seg < self.workspace.min_table_z:
                return (
                    False,
                    f"Link {idx} penetrates tabletop (min z={min_z_seg:.3f}m < {self.workspace.min_table_z}m)",
                )

        # 2. Check collisions against obstacle primitives
        for obs_idx, obstacle in enumerate(self.obstacles):
            for link_idx, (p_start, p_end) in enumerate(segments):
                # Segment distance minus link radius
                dist = obstacle.distance_to_segment(p_start, p_end)
                if dist <= self.link_radius:
                    return (
                        False,
                        f"Link {link_idx} collides with obstacle {obs_idx} ({type(obstacle).__name__}): clearance {dist - self.link_radius:.4f}m",
                    )

        return True, None

    def validate_trajectory(
        self,
        points: list[TrajectoryPoint] | list[list[float]] | list[JointConfiguration],
    ) -> tuple[bool, str | None]:
        """Validate entire trajectory sequence for collisions along the entire path.

        Returns:
            (True, None) if entire trajectory is collision-free.
            (False, reason) at the first detected collision point.
        """
        for step_idx, pt in enumerate(points):
            t_val: float = float(step_idx)
            joint_vals: JointConfiguration | list[float]
            if isinstance(pt, list):
                joint_vals = pt
            elif hasattr(pt, "positions"):
                joint_vals = pt.positions  # type: ignore[union-attr]
                if hasattr(pt, "time"):
                    t_val = float(pt.time)  # type: ignore[union-attr]
            else:
                joint_vals = pt  # type: ignore[assignment]

            is_valid, reason = self.validate_configuration(joint_vals)
            if not is_valid:
                return False, f"Collision at step {step_idx} (t={t_val:.3f}s): {reason}"

        return True, None
