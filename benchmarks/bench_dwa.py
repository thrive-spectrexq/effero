"""Benchmark for Dynamic Window Approach (DWA) local obstacle avoidance."""

from __future__ import annotations

from typing import Any

import pytest

from effero.skills.robotics.tracking.dwa import DWAController, DWAParams, RobotState


@pytest.fixture
def dwa_controller() -> DWAController:
    return DWAController(DWAParams())


def test_bench_dwa_compute_velocity(benchmark: Any, dwa_controller: DWAController) -> None:
    """Benchmark DWA velocity candidate evaluation across obstacle cluster."""
    state = RobotState(x=0.0, y=0.0, yaw=0.0, v=0.5, omega=0.0)
    goal = (5.0, 5.0)
    obstacles = [(1.5, 1.0), (2.0, 2.5), (3.0, 3.2), (4.0, 4.1)]

    def compute():
        return dwa_controller.compute_velocity(state, goal, obstacles)

    best_v, best_omega, traj = benchmark(compute)
    assert best_v > 0.0
    assert len(traj) > 0
