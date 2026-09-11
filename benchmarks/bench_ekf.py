"""Benchmark Extended Kalman Filter predict + update cycle."""

from __future__ import annotations

import math
from typing import Any

import pytest

from effero.skills.robotics.localization.ekf import (
    EKFLocalizer,
    Landmark,
    LandmarkObservation,
)


@pytest.fixture
def ekf() -> EKFLocalizer:
    """A fresh EKF instance at the origin."""
    return EKFLocalizer(initial_x=0.0, initial_y=0.0, initial_yaw=0.0, initial_v=0.0)


@pytest.fixture
def landmark_fixture() -> tuple[LandmarkObservation, Landmark]:
    obs = LandmarkObservation(landmark_id="lm1", range_m=5.0, bearing_rad=math.radians(30))
    lm = Landmark(id="lm1", x=4.0, y=3.0)
    return obs, lm


def test_predict_step(benchmark: Any, ekf: EKFLocalizer) -> None:
    """Benchmark a single EKF motion prediction step."""
    benchmark(ekf.predict, control_v=1.0, control_omega=0.1, dt=0.05)


def test_landmark_update(
    benchmark: Any, ekf: EKFLocalizer, landmark_fixture: tuple[LandmarkObservation, Landmark]
) -> None:
    """Benchmark a single EKF landmark update step."""
    obs, lm = landmark_fixture
    ekf.predict(control_v=1.0, control_omega=0.1, dt=0.05)
    benchmark(ekf.update_landmark, obs=obs, landmark=lm)


def test_predict_update_cycle(
    benchmark: Any, ekf: EKFLocalizer, landmark_fixture: tuple[LandmarkObservation, Landmark]
) -> None:
    """Benchmark a full predict-then-update cycle."""
    obs, lm = landmark_fixture

    def cycle():
        ekf.predict(control_v=1.0, control_omega=0.1, dt=0.05)
        ekf.update_landmark(obs=obs, landmark=lm)

    benchmark(cycle)
