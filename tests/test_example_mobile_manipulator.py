"""Test mobile manipulator example scenario execution."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_mobile_manipulator_module():
    example_path = Path(__file__).resolve().parents[1] / "examples" / "mobile-manipulator" / "main.py"
    spec = importlib.util.spec_from_file_location("mobile_manipulator_main", example_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_mobile_manipulator_scenario() -> None:
    """Verify autonomous mobile manipulator scenario runs successfully and publishes CDR telemetry."""
    module = _load_mobile_manipulator_module()
    example_dir = Path(__file__).resolve().parents[1] / "examples" / "mobile-manipulator"
    config_path = example_dir / "effero.yaml"
    assert config_path.exists()

    result = await module.run_scenario(config_path)
    assert result["status"] == "success"
    assert result["published_frames"] >= 5  # Nav and arm trajectories published to ROS 2 bridge
    assert result["final_arm_position"] is not None
