"""Benchmark Extended Kalman Filter predict + update cycle."""

import math

import pytest

from effero.skills.robotics.localization.ekf import ExtendedKalmanFilter


@pytest.fixture
def ekf():
    """A fresh EKF instance at the origin."""
    return ExtendedKalmanFilter(x=0.0, y=0.0, theta=0.0)


def test_predict_step(benchmark, ekf):
    """Benchmark a single EKF motion prediction step."""
    benchmark(ekf.predict, v=1.0, omega=0.1, dt=0.05)


def test_landmark_update(benchmark, ekf):
    """Benchmark a single EKF landmark update step."""
    # First do a predict so state is non-trivial
    ekf.predict(v=1.0, omega=0.1, dt=0.05)
    benchmark(
        ekf.update_landmark,
        measured_range=5.0,
        measured_bearing=math.radians(30),
        landmark_x=4.0,
        landmark_y=3.0,
    )


def test_predict_update_cycle(benchmark, ekf):
    """Benchmark a full predict-then-update cycle."""

    def cycle():
        ekf.predict(v=1.0, omega=0.1, dt=0.05)
        ekf.update_landmark(
            measured_range=5.0,
            measured_bearing=math.radians(30),
            landmark_x=4.0,
            landmark_y=3.0,
        )

    benchmark(cycle)
