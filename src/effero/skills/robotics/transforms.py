"""Spatial transformations algebra for 2D (SE2) and 3D (SE3) coordinate frames.

Inspired by NumPy vector math, modern robotics kinematics, and ROS tf2.
Provides homogeneous transformations, frame chaining with the '@' operator,
exact matrix inverses, and point transforms.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def wrap_angle(angle: float) -> float:
    """Normalize angle to (-pi, pi]."""
    w = math.atan2(math.sin(angle), math.cos(angle))
    if abs(w + math.pi) < 1e-12:
        return math.pi
    return w


@dataclass
class Transform2D:
    """Homogeneous coordinate transformation in SE(2) representing (x, y, theta)."""

    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0

    def __post_init__(self) -> None:
        self.x = float(self.x)
        self.y = float(self.y)
        self.theta = wrap_angle(float(self.theta))

    @classmethod
    def identity(cls) -> Transform2D:
        """Return the identity transform (0, 0, 0)."""
        return cls(0.0, 0.0, 0.0)

    @classmethod
    def from_tuple(cls, coords: tuple[float, float, float]) -> Transform2D:
        """Construct Transform2D from (x, y, theta) tuple."""
        return cls(coords[0], coords[1], coords[2])

    def to_tuple(self) -> tuple[float, float, float]:
        """Return (x, y, theta) tuple."""
        return (self.x, self.y, self.theta)

    @property
    def matrix(self) -> list[list[float]]:
        """Return 3x3 homogeneous transformation matrix."""
        c = math.cos(self.theta)
        s = math.sin(self.theta)
        return [
            [c, -s, self.x],
            [s, c, self.y],
            [0.0, 0.0, 1.0],
        ]

    def compose(self, other: Transform2D) -> Transform2D:
        """Compose this transform with another: T_result = self * other."""
        c = math.cos(self.theta)
        s = math.sin(self.theta)
        new_x = self.x + other.x * c - other.y * s
        new_y = self.y + other.x * s + other.y * c
        new_theta = wrap_angle(self.theta + other.theta)
        return Transform2D(x=new_x, y=new_y, theta=new_theta)

    def __matmul__(self, other: Transform2D) -> Transform2D:
        """Compose transforms using Python matrix multiplication operator '@'."""
        if not isinstance(other, Transform2D):
            return NotImplemented
        return self.compose(other)

    def inverse(self) -> Transform2D:
        """Compute exact analytical inverse transformation T^-1."""
        c = math.cos(self.theta)
        s = math.sin(self.theta)
        inv_x = -self.x * c - self.y * s
        inv_y = self.x * s - self.y * c
        inv_theta = wrap_angle(-self.theta)
        return Transform2D(x=inv_x, y=inv_y, theta=inv_theta)

    def transform_point(self, px: float, py: float) -> tuple[float, float]:
        """Transform point (px, py) from local child frame into parent frame."""
        c = math.cos(self.theta)
        s = math.sin(self.theta)
        tx = self.x + px * c - py * s
        ty = self.y + px * s + py * c
        return (tx, ty)

    def inverse_transform_point(self, px: float, py: float) -> tuple[float, float]:
        """Transform point (px, py) from parent frame into local child frame."""
        return self.inverse().transform_point(px, py)

    def distance_to(self, other: Transform2D) -> float:
        """Euclidean translation distance between two transforms."""
        return math.hypot(other.x - self.x, other.y - self.y)

    def angular_distance_to(self, other: Transform2D) -> float:
        """Shortest angular distance in radians between two orientations."""
        return abs(wrap_angle(other.theta - self.theta))


@dataclass
class Transform3D:
    """Homogeneous coordinate transformation in SE(3) with translation and Euler rotation (roll, pitch, yaw)."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0

    def __post_init__(self) -> None:
        self.x = float(self.x)
        self.y = float(self.y)
        self.z = float(self.z)
        self.roll = wrap_angle(float(self.roll))
        self.pitch = wrap_angle(float(self.pitch))
        self.yaw = wrap_angle(float(self.yaw))

    @classmethod
    def identity(cls) -> Transform3D:
        """Return the identity SE(3) transform."""
        return cls(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    @property
    def rotation_matrix(self) -> list[list[float]]:
        """Return 3x3 direction cosine rotation matrix (Z-Y-X Tait-Bryan angles)."""
        cr = math.cos(self.roll)
        sr = math.sin(self.roll)
        cp = math.cos(self.pitch)
        sp = math.sin(self.pitch)
        cy = math.cos(self.yaw)
        sy = math.sin(self.yaw)

        # R = Rz(yaw) * Ry(pitch) * Rx(roll)
        r00 = cy * cp
        r01 = cy * sp * sr - sy * cr
        r02 = cy * sp * cr + sy * sr

        r10 = sy * cp
        r11 = sy * sp * sr + cy * cr
        r12 = sy * sp * cr - cy * sr

        r20 = -sp
        r21 = cp * sr
        r22 = cp * cr

        return [
            [r00, r01, r02],
            [r10, r11, r12],
            [r20, r21, r22],
        ]

    @property
    def matrix(self) -> list[list[float]]:
        """Return 4x4 homogeneous transformation matrix."""
        r = self.rotation_matrix
        return [
            [r[0][0], r[0][1], r[0][2], self.x],
            [r[1][0], r[1][1], r[1][2], self.y],
            [r[2][0], r[2][1], r[2][2], self.z],
            [0.0, 0.0, 0.0, 1.0],
        ]

    def transform_point(self, px: float, py: float, pz: float) -> tuple[float, float, float]:
        """Transform 3D point from child frame into parent frame."""
        r = self.rotation_matrix
        tx = self.x + r[0][0] * px + r[0][1] * py + r[0][2] * pz
        ty = self.y + r[1][0] * px + r[1][1] * py + r[1][2] * pz
        tz = self.z + r[2][0] * px + r[2][1] * py + r[2][2] * pz
        return (tx, ty, tz)

    def inverse(self) -> Transform3D:
        """Compute exact analytical inverse transformation T^-1."""
        r = self.rotation_matrix
        # Transpose rotation R^T
        rt = [
            [r[0][0], r[1][0], r[2][0]],
            [r[0][1], r[1][1], r[2][1]],
            [r[0][2], r[1][2], r[2][2]],
        ]
        # inv_t = -R^T * t
        inv_x = -(rt[0][0] * self.x + rt[0][1] * self.y + rt[0][2] * self.z)
        inv_y = -(rt[1][0] * self.x + rt[1][1] * self.y + rt[1][2] * self.z)
        inv_z = -(rt[2][0] * self.x + rt[2][1] * self.y + rt[2][2] * self.z)

        # Extract roll, pitch, yaw from R^T
        pitch = math.atan2(-rt[2][0], math.hypot(rt[2][1], rt[2][2]))
        if abs(math.cos(pitch)) > 1e-6:
            roll = math.atan2(rt[2][1], rt[2][2])
            yaw = math.atan2(rt[1][0], rt[0][0])
        else:
            roll = 0.0
            yaw = math.atan2(-rt[0][1], rt[1][1])

        return Transform3D(x=inv_x, y=inv_y, z=inv_z, roll=roll, pitch=pitch, yaw=yaw)

    def compose(self, other: Transform3D) -> Transform3D:
        """Compose this transform with another: T_result = self * other."""
        # Calculate new translation
        p_other = self.transform_point(other.x, other.y, other.z)

        # Multiply rotation matrices R = R1 * R2
        r1 = self.rotation_matrix
        r2 = other.rotation_matrix
        r = [[0.0, 0.0, 0.0] for _ in range(3)]
        for i in range(3):
            for j in range(3):
                r[i][j] = sum(r1[i][k] * r2[k][j] for k in range(3))

        # Extract roll, pitch, yaw from R
        pitch = math.atan2(-r[2][0], math.hypot(r[2][1], r[2][2]))
        if abs(math.cos(pitch)) > 1e-6:
            roll = math.atan2(r[2][1], r[2][2])
            yaw = math.atan2(r[1][0], r[0][0])
        else:
            roll = 0.0
            yaw = math.atan2(-r[0][1], r[1][1])

        return Transform3D(
            x=p_other[0],
            y=p_other[1],
            z=p_other[2],
            roll=roll,
            pitch=pitch,
            yaw=yaw,
        )

    def __matmul__(self, other: Transform3D) -> Transform3D:
        """Compose 3D transforms using '@' operator."""
        if not isinstance(other, Transform3D):
            return NotImplemented
        return self.compose(other)

    @property
    def quaternion(self) -> tuple[float, float, float, float]:
        """Convert orientation to unit quaternion (qx, qy, qz, qw)."""
        cy = math.cos(self.yaw * 0.5)
        sy = math.sin(self.yaw * 0.5)
        cp = math.cos(self.pitch * 0.5)
        sp = math.sin(self.pitch * 0.5)
        cr = math.cos(self.roll * 0.5)
        sr = math.sin(self.roll * 0.5)

        qw = cr * cp * cy + sr * sp * sy
        qx = sr * cp * cy - cr * sp * sy
        qy = cr * sp * cy + sr * cp * sy
        qz = cr * cp * sy - sr * sp * cy

        norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
        if norm > 1e-9:
            return (qx / norm, qy / norm, qz / norm, qw / norm)
        return (0.0, 0.0, 0.0, 1.0)

    @classmethod
    def from_quaternion(
        cls,
        x: float,
        y: float,
        z: float,
        qx: float,
        qy: float,
        qz: float,
        qw: float,
    ) -> Transform3D:
        """Construct Transform3D from translation and unit quaternion."""
        # roll (x-axis rotation)
        sinr_cosp = 2.0 * (qw * qx + qy * qz)
        cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
        roll = math.atan2(sinr_cosp, cosr_cosp)

        # pitch (y-axis rotation)
        sinp = 2.0 * (qw * qy - qz * qx)
        if abs(sinp) >= 1:
            pitch = math.copysign(math.pi / 2.0, sinp)
        else:
            pitch = math.asin(sinp)

        # yaw (z-axis rotation)
        siny_cosp = 2.0 * (qw * qz + qx * qy)
        cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        return cls(x=x, y=y, z=z, roll=roll, pitch=pitch, yaw=yaw)
