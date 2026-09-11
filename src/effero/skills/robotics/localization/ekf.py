"""Extended Kalman Filter (EKF) Localization for mobile robots.

Fuses wheel odometry/kinematic motion model with landmark observations (range & bearing)
and direct position fixes (GPS/UWB/vision fiducials). Inspired by PythonRobotics Localization.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from effero.skills.robotics.tracking.dwa import normalize_angle


@dataclass
class Landmark:
    """Known stationary spatial landmark in world coordinate frame."""

    id: str
    x: float
    y: float


@dataclass
class LandmarkObservation:
    """Relative sensor measurement of a landmark."""

    landmark_id: str
    range_m: float
    bearing_rad: float


@dataclass
class EKFState:
    """Estimated state vector and uncertainty confidence."""

    x: float
    y: float
    yaw: float
    v: float
    covariance: list[list[float]]

    @property
    def uncertainty_radius(self) -> float:
        """2-sigma spatial uncertainty radius in meters."""
        var_x = self.covariance[0][0]
        var_y = self.covariance[1][1]
        return 2.0 * math.sqrt(max(var_x + var_y, 1e-6))

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "yaw_radians": round(self.yaw, 4),
            "yaw_degrees": round(math.degrees(self.yaw), 2),
            "velocity": round(self.v, 4),
            "uncertainty_radius_m": round(self.uncertainty_radius, 4),
            "variance_x": round(self.covariance[0][0], 6),
            "variance_y": round(self.covariance[1][1], 6),
            "variance_yaw": round(self.covariance[2][2], 6),
        }


# Helper matrix operations for fixed small dimensions
def _matmul(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    rows_A = len(A)
    cols_A = len(A[0])
    rows_B = len(B)
    cols_B = len(B[0])
    if cols_A != rows_B:
        raise ValueError(f"Matrix shape mismatch: {rows_A}x{cols_A} and {rows_B}x{cols_B}")

    C = [[0.0] * cols_B for _ in range(rows_A)]
    for i in range(rows_A):
        for j in range(cols_B):
            s = 0.0
            for k in range(cols_A):
                s += A[i][k] * B[k][j]
            C[i][j] = s
    return C


def _transpose(A: list[list[float]]) -> list[list[float]]:
    rows = len(A)
    cols = len(A[0])
    return [[A[i][j] for i in range(rows)] for j in range(cols)]


def _inv2x2(M: list[list[float]]) -> list[list[float]]:
    """Invert a 2x2 matrix."""
    a, b = M[0][0], M[0][1]
    c, d = M[1][0], M[1][1]
    det = a * d - b * c
    if abs(det) < 1e-12:
        det = 1e-12
    inv_det = 1.0 / det
    return [
        [d * inv_det, -b * inv_det],
        [-c * inv_det, a * inv_det],
    ]


class EKFLocalizer:
    """Extended Kalman Filter estimating [x, y, yaw, v] with covariance propagation."""

    def __init__(
        self,
        initial_x: float = 0.0,
        initial_y: float = 0.0,
        initial_yaw: float = 0.0,
        initial_v: float = 0.0,
        pos_var: float = 0.1,
        yaw_var: float = math.radians(5.0) ** 2,
        v_var: float = 0.1,
    ) -> None:
        # State vector: [x, y, yaw, v]
        self.x = initial_x
        self.y = initial_y
        self.yaw = initial_yaw
        self.v = initial_v

        # 4x4 State Covariance Matrix P
        self.P: list[list[float]] = [
            [pos_var, 0.0, 0.0, 0.0],
            [0.0, pos_var, 0.0, 0.0],
            [0.0, 0.0, yaw_var, 0.0],
            [0.0, 0.0, 0.0, v_var],
        ]

        # Process noise covariance Q
        self.Q: list[list[float]] = [
            [0.05**2, 0.0, 0.0, 0.0],
            [0.0, 0.05**2, 0.0, 0.0],
            [0.0, 0.0, math.radians(2.0) ** 2, 0.0],
            [0.0, 0.0, 0.0, 0.05**2],
        ]

        # Landmark measurement noise covariance R (range, bearing)
        self.R_landmark: list[list[float]] = [
            [0.1**2, 0.0],
            [0.0, math.radians(3.0) ** 2],
        ]

        # GPS / absolute position measurement noise covariance R
        self.R_pos: list[list[float]] = [
            [0.2**2, 0.0],
            [0.0, 0.2**2],
        ]

    def predict(self, control_v: float, control_omega: float, dt: float) -> EKFState:
        """Predict next state using non-linear differential-drive motion model."""
        # Kinematic state transition
        next_yaw = normalize_angle(self.yaw + control_omega * dt)
        next_x = self.x + control_v * math.cos(self.yaw) * dt
        next_y = self.y + control_v * math.sin(self.yaw) * dt
        next_v = control_v

        # Jacobian of motion model F with respect to state x: dF/dx
        F = [
            [1.0, 0.0, -control_v * math.sin(self.yaw) * dt, math.cos(self.yaw) * dt],
            [0.0, 1.0, control_v * math.cos(self.yaw) * dt, math.sin(self.yaw) * dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]

        # Covariance propagation: P_pred = F * P * F^T + Q
        FP = _matmul(F, self.P)
        FPF_T = _matmul(FP, _transpose(F))
        P_pred = [[FPF_T[i][j] + self.Q[i][j] for j in range(4)] for i in range(4)]

        self.x = next_x
        self.y = next_y
        self.yaw = next_yaw
        self.v = next_v
        self.P = P_pred

        return self.get_state()

    def update_landmark(self, obs: LandmarkObservation, landmark: Landmark) -> EKFState:
        """Update state using range and bearing measurement to a known landmark."""
        dx = landmark.x - self.x
        dy = landmark.y - self.y
        dist = math.hypot(dx, dy)
        if dist < 1e-4:
            return self.get_state()

        expected_range = dist
        expected_bearing = normalize_angle(math.atan2(dy, dx) - self.yaw)

        # Innovation (residual) y = z - h(x)
        res_range = obs.range_m - expected_range
        res_bearing = normalize_angle(obs.bearing_rad - expected_bearing)
        y = [[res_range], [res_bearing]]

        # Measurement Jacobian H (2x4)
        H = [
            [-dx / dist, -dy / dist, 0.0, 0.0],
            [dy / (dist**2), -dx / (dist**2), -1.0, 0.0],
        ]

        # S = H * P * H^T + R
        HP = _matmul(H, self.P)
        HPH_T = _matmul(HP, _transpose(H))
        S = [[HPH_T[i][j] + self.R_landmark[i][j] for j in range(2)] for i in range(2)]

        # Kalman Gain: K = P * H^T * S^-1 (4x2)
        S_inv = _inv2x2(S)
        P_HT = _matmul(self.P, _transpose(H))
        K = _matmul(P_HT, S_inv)

        # State correction: dx = K * y
        dx_corr = _matmul(K, y)
        self.x += dx_corr[0][0]
        self.y += dx_corr[1][0]
        self.yaw = normalize_angle(self.yaw + dx_corr[2][0])
        self.v += dx_corr[3][0]

        # Covariance update: P = (I - K * H) * P
        KH = _matmul(K, H)
        I4 = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
        I_KH = [[I4[i][j] - KH[i][j] for j in range(4)] for i in range(4)]
        self.P = _matmul(I_KH, self.P)

        return self.get_state()

    def update_position(
        self,
        measured_x: float,
        measured_y: float,
        measurement_std_dev: float = 0.2,
    ) -> EKFState:
        """Update state using an absolute 2D position fix (GPS, UWB, or vision fiducial)."""
        # Innovation y = z - h(x)
        y = [[measured_x - self.x], [measured_y - self.y]]

        # Measurement Jacobian H (2x4)
        H = [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ]

        R = [
            [measurement_std_dev**2, 0.0],
            [0.0, measurement_std_dev**2],
        ]

        HP = _matmul(H, self.P)
        HPH_T = _matmul(HP, _transpose(H))
        S = [[HPH_T[i][j] + R[i][j] for j in range(2)] for i in range(2)]

        S_inv = _inv2x2(S)
        P_HT = _matmul(self.P, _transpose(H))
        K = _matmul(P_HT, S_inv)

        dx_corr = _matmul(K, y)
        self.x += dx_corr[0][0]
        self.y += dx_corr[1][0]
        self.yaw = normalize_angle(self.yaw + dx_corr[2][0])
        self.v += dx_corr[3][0]

        KH = _matmul(K, H)
        I4 = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
        I_KH = [[I4[i][j] - KH[i][j] for j in range(4)] for i in range(4)]
        self.P = _matmul(I_KH, self.P)

        return self.get_state()

    def get_state(self) -> EKFState:
        """Return a copy of the current state and covariance."""
        return EKFState(
            x=self.x,
            y=self.y,
            yaw=self.yaw,
            v=self.v,
            covariance=[row[:] for row in self.P],
        )


# Backward-compatibility alias
ExtendedKalmanFilter = EKFLocalizer
