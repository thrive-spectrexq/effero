"""Tests for Vision-Language-Action (VLA) policy runner."""

from __future__ import annotations

from PIL import Image

from effero.perception.vision.vla import VLAAction, VLAPolicyRunner


def test_vla_action_dataclass() -> None:
    act = VLAAction(dx=0.01, dy=-0.02, dz=0.03, gripper=-1.0)
    d = act.to_dict()
    assert d["dx"] == 0.01
    assert d["dy"] == -0.02
    assert d["dz"] == 0.03
    assert d["gripper"] == -1.0


def test_vla_policy_inference_and_smoothing() -> None:
    runner = VLAPolicyRunner(smoothing_factor=0.5)

    # 100x100 RGB image
    img = Image.new("RGB", (100, 100), color=(120, 80, 40))

    # Test forward and grasp
    action1 = runner.predict_action(img, "reach forward and grasp the cup")
    assert action1.dx > 0.0
    assert action1.gripper == -1.0

    # Test smoothed second action
    action2 = runner.predict_action(img, "lift up and release")
    assert action2.dz > 0.0
    assert action2.gripper == 1.0


def test_vla_action_execution_on_arm() -> None:
    runner = VLAPolicyRunner()
    action = VLAAction(dx=0.02, dy=0.01, dz=0.0, gripper=-1.0)

    res = runner.execute_action(action)
    assert res["status"] == "success"
    assert "position" in res
