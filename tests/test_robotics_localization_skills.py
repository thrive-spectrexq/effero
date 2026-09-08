"""Integration tests for NavigationController EKF localization and localization skills."""

from __future__ import annotations

import pytest

from effero.skills.robotics.navigate import (
    NavigationController,
    localize_landmark,
    localize_position_fix,
    localize_predict,
)


@pytest.mark.asyncio
async def test_localize_predict_skill() -> None:
    res = await localize_predict(control_v=0.5, control_omega=0.1, dt=0.2)
    assert res["status"] == "success"
    assert "state" in res
    assert "uncertainty_radius_m" in res["state"]
    assert res["state"]["velocity"] == 0.5


@pytest.mark.asyncio
async def test_localize_landmark_skill() -> None:
    # Kitchen is a default preloaded landmark at (3.5, 1.2)
    res = await localize_landmark(
        landmark_id="kitchen",
        range_m=3.69,
        bearing_rad=0.33,
    )
    assert res["status"] == "success"
    assert "state" in res


@pytest.mark.asyncio
async def test_localize_landmark_unknown_landmark() -> None:
    res = await localize_landmark(
        landmark_id="non_existent_landmark",
        range_m=10.0,
        bearing_rad=0.0,
    )
    assert res["status"] == "error"
    assert "not found" in res["message"]


@pytest.mark.asyncio
async def test_localize_position_fix_skill() -> None:
    res = await localize_position_fix(x=1.0, y=2.0, std_dev=0.1)
    assert res["status"] == "success"
    assert "state" in res
    assert res["state"]["x"] > 0.1  # Pulled significantly towards measured x=1.0
    assert res["state"]["y"] > 1.0  # Pulled significantly towards measured y=2.0
    assert res["state"]["uncertainty_radius_m"] < 0.4


def test_navigation_controller_telemetry_includes_ekf() -> None:
    controller = NavigationController()
    telemetry = controller.get_telemetry()
    assert "ekf_localization" in telemetry
    assert "uncertainty_radius_m" in telemetry["ekf_localization"]
    assert "variance_x" in telemetry["ekf_localization"]
