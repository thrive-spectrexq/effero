"""Comprehensive tests for ONNX local VLA inference engine, smoothing filters, and kinematic safety."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np
import onnx
import pytest
from PIL import Image

from effero.perception.vision.vla import (
    EMASmoothingFilter,
    ONNXVLAEngine,
    RollingWindowSmoothingFilter,
    VLAAction,
    VLAPolicyRunner,
    clamp_action_delta,
    encode_instruction,
    export_vla_onnx_model,
    preprocess_image,
    vla_step,
)


def test_export_vla_onnx_model() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = Path(tmpdir) / "test_vla.onnx"
        exported_path = export_vla_onnx_model(model_path, feature_dim=64)

        assert Path(exported_path).exists()
        model = onnx.load(exported_path)
        onnx.checker.check_model(model)

        # Validate inputs and outputs
        input_names = [i.name for i in model.graph.input]
        output_names = [o.name for o in model.graph.output]

        assert "image" in input_names
        assert "instruction" in input_names
        assert "action" in output_names
        assert "confidence" in output_names


def test_preprocess_image() -> None:
    # Test with PIL Image
    pil_img = Image.new("RGB", (320, 240), color=(100, 150, 200))
    tensor1 = preprocess_image(pil_img)
    assert tensor1.shape == (1, 3, 224, 224)
    assert tensor1.dtype == np.float32

    # Test with NumPy Array
    np_img = np.zeros((480, 640, 3), dtype=np.uint8)
    tensor2 = preprocess_image(np_img)
    assert tensor2.shape == (1, 3, 224, 224)
    assert tensor2.dtype == np.float32

    # Zero dimension error handling
    zero_img = Image.new("RGB", (0, 0))
    with pytest.raises(ValueError, match="zero dimensions"):
        preprocess_image(zero_img)


def test_encode_instruction() -> None:
    vec_forward = encode_instruction("move forward to the table")
    assert vec_forward.shape == (1, 64)
    assert vec_forward[0, 0] > 0.0, "Forward keyword should produce positive x delta"

    vec_back = encode_instruction("step backward")
    assert vec_back[0, 0] < 0.0, "Backward keyword should produce negative x delta"

    vec_right = encode_instruction("shift to the right")
    assert vec_right[0, 1] > 0.0, "Right keyword should produce positive y delta"

    vec_left = encode_instruction("shift left")
    assert vec_left[0, 1] < 0.0, "Left keyword should produce negative y delta"

    vec_up = encode_instruction("lift up the object")
    assert vec_up[0, 2] > 0.0, "Up keyword should produce positive z delta"

    vec_down = encode_instruction("descend down")
    assert vec_down[0, 2] < 0.0, "Down keyword should produce negative z delta"

    vec_open = encode_instruction("release and open gripper")
    assert vec_open[0, 3] > 0.0, "Open keyword should produce positive gripper delta"

    vec_close = encode_instruction("grasp and close gripper")
    assert vec_close[0, 3] < 0.0, "Close keyword should produce negative gripper delta"

    # L2 unit normalization check
    norm = float(np.linalg.norm(vec_forward))
    assert math.isclose(norm, 1.0, rel_tol=1e-3)


def test_onnx_vla_engine_inference() -> None:
    engine = ONNXVLAEngine()
    img = Image.new("RGB", (200, 200), color=(50, 120, 200))

    # Test forward and grasp
    action1 = engine.predict_action(img, "reach forward and grasp the red cup")
    assert isinstance(action1, VLAAction)
    assert action1.dx > 0.0, "Action dx should be forward (positive)"
    assert action1.gripper == -1.0, "Gripper should be closed (-1.0)"
    assert 0.0 <= action1.confidence <= 1.0

    # Test lift and release
    action2 = engine.predict_action(img, "lift up and release")
    assert isinstance(action2, VLAAction)
    assert action2.dz > 0.0, "Action dz should be up (positive)"
    assert action2.gripper == 1.0, "Gripper should be open (+1.0)"

    # Test with direct numpy embedding
    inst_vec = np.zeros((1, 64), dtype=np.float32)
    inst_vec[0, 1] = 1.0  # right
    action3 = engine.predict_action(img, inst_vec)
    assert action3.dy > 0.0, "Action dy should be right (positive)"


def test_ema_smoothing_filter() -> None:
    ema = EMASmoothingFilter(smoothing_factor=0.6)

    a1 = VLAAction(dx=0.10, dy=0.0, dz=0.0, confidence=0.8)
    s1 = ema.update(a1)
    # First action passes directly
    assert s1.dx == 0.10
    assert s1.confidence == 0.8

    # Second action: expected dx = 0.6 * 0.10 + 0.4 * 0.20 = 0.06 + 0.08 = 0.14
    a2 = VLAAction(dx=0.20, dy=0.0, dz=0.0, confidence=1.0)
    s2 = ema.update(a2)
    assert math.isclose(s2.dx, 0.14, rel_tol=1e-4)
    assert math.isclose(s2.confidence, 0.6 * 0.8 + 0.4 * 1.0, rel_tol=1e-4)

    # Reset
    ema.reset()
    s3 = ema.update(a2)
    assert s3.dx == 0.20


def test_rolling_window_smoothing_filter() -> None:
    # Uniform 3-tap window filter
    rolling = RollingWindowSmoothingFilter(window_size=3, weights=[1.0, 1.0, 1.0])

    a1 = VLAAction(dx=0.03, dy=0.0, dz=0.0)
    a2 = VLAAction(dx=0.06, dy=0.0, dz=0.0)
    a3 = VLAAction(dx=0.09, dy=0.0, dz=0.0)

    # Step 1: history = [0.03] -> avg = 0.03
    s1 = rolling.update(a1)
    assert math.isclose(s1.dx, 0.03, rel_tol=1e-4)

    # Step 2: history = [0.03, 0.06] -> avg = 0.045
    s2 = rolling.update(a2)
    assert math.isclose(s2.dx, 0.045, rel_tol=1e-4)

    # Step 3: history = [0.03, 0.06, 0.09] -> avg = 0.06
    s3 = rolling.update(a3)
    assert math.isclose(s3.dx, 0.06, rel_tol=1e-4)

    # Step 4: new action 0.12 replaces 0.03 -> history = [0.06, 0.09, 0.12] -> avg = 0.09
    a4 = VLAAction(dx=0.12, dy=0.0, dz=0.0)
    s4 = rolling.update(a4)
    assert math.isclose(s4.dx, 0.09, rel_tol=1e-4)


def test_kinematic_clamping() -> None:
    # Test Cartesian translation clamping
    oversized_action = VLAAction(dx=0.3, dy=0.4, dz=0.0)  # norm = 0.5m
    clamped = clamp_action_delta(oversized_action, max_step_size=0.05, max_rotation_step=0.1)

    clamped_norm = math.sqrt(clamped.dx**2 + clamped.dy**2 + clamped.dz**2)
    assert math.isclose(clamped_norm, 0.05, rel_tol=1e-4)
    # Direction preserved: dx/dy ratio remains 0.3/0.4 = 0.75
    assert math.isclose(clamped.dx / clamped.dy, 0.75, rel_tol=1e-4)

    # Test rotational clamping
    oversized_rot = VLAAction(dx=0.01, dy=0.01, dz=0.01, droll=0.6, dpitch=0.8, dyaw=0.0)
    clamped_rot = clamp_action_delta(oversized_rot, max_step_size=0.05, max_rotation_step=0.2)
    rot_norm = math.sqrt(clamped_rot.droll**2 + clamped_rot.dpitch**2 + clamped_rot.dyaw**2)
    assert math.isclose(rot_norm, 0.2, rel_tol=1e-4)


def test_vla_policy_runner_with_rolling_filter() -> None:
    runner = VLAPolicyRunner(filter_type="rolling", max_step_size=0.05)
    img = Image.new("RGB", (100, 100), color=(100, 100, 100))

    act = runner.predict_action(img, "reach forward and grasp")
    assert act.dx > 0.0
    assert act.gripper == -1.0

    res = runner.execute_action(act)
    assert res["status"] == "success"
    assert "position" in res


@pytest.mark.asyncio
async def test_vla_step_skill() -> None:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img = Image.new("RGB", (128, 128), color=(80, 160, 240))
        img.save(tmp.name)
        img_path = tmp.name

    res = await vla_step(img_path, "lift up and release")
    assert res["status"] == "success"
    assert "predicted_action" in res
    assert "execution_result" in res
    assert res["predicted_action"]["gripper"] == 1.0
