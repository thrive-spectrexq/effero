"""Unit tests for Extended Kalman Filter (EKF) localization and covariance propagation."""

from __future__ import annotations

import math

from effero.skills.robotics.localization.ekf import (
    EKFLocalizer,
    Landmark,
    LandmarkObservation,
    _inv2x2,
    _matmul,
    _transpose,
)


def test_matrix_helpers() -> None:
    A = [[1.0, 2.0], [3.0, 4.0]]
    B = [[2.0, 0.0], [1.0, 2.0]]
    # Matmul
    C = _matmul(A, B)
    assert C == [[4.0, 4.0], [10.0, 8.0]]

    # Transpose
    AT = _transpose(A)
    assert AT == [[1.0, 3.0], [2.0, 4.0]]

    # Invert 2x2
    invA = _inv2x2(A)
    # A * invA should be identity
    ident = _matmul(A, invA)
    assert math.isclose(ident[0][0], 1.0, abs_tol=1e-6)
    assert math.isclose(ident[0][1], 0.0, abs_tol=1e-6)
    assert math.isclose(ident[1][0], 0.0, abs_tol=1e-6)
    assert math.isclose(ident[1][1], 1.0, abs_tol=1e-6)


def test_ekf_prediction_step_uncertainty_growth() -> None:
    ekf = EKFLocalizer(initial_x=0.0, initial_y=0.0, initial_yaw=0.0, initial_v=0.0, pos_var=0.05)
    initial_unc = ekf.get_state().uncertainty_radius

    # Drive forward at 1.0 m/s for 1 second
    state = ekf.predict(control_v=1.0, control_omega=0.0, dt=1.0)

    # Position should advance by 1.0m
    assert math.isclose(state.x, 1.0, abs_tol=1e-3)
    assert math.isclose(state.y, 0.0, abs_tol=1e-3)
    assert state.v == 1.0

    # In pure dead-reckoning without measurements, process noise Q causes uncertainty to grow
    assert state.uncertainty_radius > initial_unc


def test_ekf_landmark_update_reduces_uncertainty() -> None:
    # Initialize robot with large position uncertainty (pos_var = 1.0)
    ekf = EKFLocalizer(initial_x=0.2, initial_y=-0.3, initial_yaw=0.0, pos_var=1.0)
    unc_before = ekf.get_state().uncertainty_radius

    # Landmark is placed at (5.0, 0.0)
    # Actual true robot is at (0.0, 0.0), so true range=5.0, true bearing=0.0
    lm = Landmark(id="beacon_1", x=5.0, y=0.0)
    obs = LandmarkObservation(landmark_id="beacon_1", range_m=5.0, bearing_rad=0.0)

    state = ekf.update_landmark(obs, lm)

    # State should correct towards true origin (x closer to 0.0, y closer to 0.0)
    assert abs(state.x) < 0.2
    assert abs(state.y) < 0.3

    # Uncertainty radius must shrink significantly after observing a landmark
    assert state.uncertainty_radius < unc_before


def test_ekf_position_fix_update() -> None:
    ekf = EKFLocalizer(initial_x=1.0, initial_y=1.0, pos_var=0.5)
    unc_before = ekf.get_state().uncertainty_radius

    # Direct position fix at (0.0, 0.0) with tight sensor accuracy (std_dev = 0.05m)
    state = ekf.update_position(measured_x=0.0, measured_y=0.0, measurement_std_dev=0.05)

    # State estimate should pull sharply towards (0.0, 0.0)
    assert state.x < 0.2
    assert state.y < 0.2
    assert state.uncertainty_radius < unc_before
