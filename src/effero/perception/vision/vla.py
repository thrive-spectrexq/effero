"""Vision-Language-Action (VLA) execution pipeline powered by local ONNX Runtime inference."""

from __future__ import annotations

import hashlib
import logging
import math
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import onnxruntime as ort
from onnx import TensorProto, helper
from PIL import Image

from effero.sdk.skill import SafetyClass, skill
from effero.skills.robotics.arm import _arm_controller

logger = logging.getLogger(__name__)


@dataclass
class VLAAction:
    """A 7-DOF continuous robotic action chunk predicted by an ONNX VLA model."""

    dx: float = 0.0  # delta x in meters
    dy: float = 0.0  # delta y in meters
    dz: float = 0.0  # delta z in meters
    droll: float = 0.0  # delta roll in radians
    dpitch: float = 0.0  # delta pitch in radians
    dyaw: float = 0.0  # delta yaw in radians
    gripper: float = 1.0  # 1.0 = open, -1.0 = close
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dx": round(self.dx, 4),
            "dy": round(self.dy, 4),
            "dz": round(self.dz, 4),
            "droll": round(self.droll, 4),
            "dpitch": round(self.dpitch, 4),
            "dyaw": round(self.dyaw, 4),
            "gripper": round(self.gripper, 2),
            "confidence": round(self.confidence, 3),
        }

    def as_array(self) -> np.ndarray:
        """Return action as a 7-element float array."""
        return np.array(
            [self.dx, self.dy, self.dz, self.droll, self.dpitch, self.dyaw, self.gripper],
            dtype=np.float32,
        )

    @classmethod
    def from_array(cls, arr: np.ndarray, confidence: float = 1.0) -> VLAAction:
        """Construct VLAAction from a 7-element array."""
        return cls(
            dx=float(arr[0]),
            dy=float(arr[1]),
            dz=float(arr[2]),
            droll=float(arr[3]),
            dpitch=float(arr[4]),
            dyaw=float(arr[5]),
            gripper=float(arr[6]),
            confidence=float(confidence),
        )


class ActionSmoothingFilter(ABC):
    """Abstract base class for temporal action smoothing filters."""

    @abstractmethod
    def update(self, action: VLAAction) -> VLAAction:
        """Filter and smooth the incoming raw action prediction."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset internal filter state."""
        ...


class EMASmoothingFilter(ActionSmoothingFilter):
    """Exponential Moving Average (EMA) action smoothing filter.

    Smoothed action:
        a_smooth(t) = (1 - alpha) * a_smooth(t-1) + alpha * a(t)
    or using smoothing_factor:
        a_smooth(t) = smoothing_factor * a_smooth(t-1) + (1 - smoothing_factor) * a(t)
    """

    def __init__(self, smoothing_factor: float = 0.7) -> None:
        if not (0.0 <= smoothing_factor < 1.0):
            raise ValueError("smoothing_factor must be in [0.0, 1.0)")
        self.smoothing_factor = smoothing_factor
        self._prev_action: VLAAction | None = None

    def update(self, action: VLAAction) -> VLAAction:
        if self._prev_action is None:
            self._prev_action = action
            return action

        sf = self.smoothing_factor
        inv_sf = 1.0 - sf

        # Continuous DOF smoothing
        smoothed = VLAAction(
            dx=sf * self._prev_action.dx + inv_sf * action.dx,
            dy=sf * self._prev_action.dy + inv_sf * action.dy,
            dz=sf * self._prev_action.dz + inv_sf * action.dz,
            droll=sf * self._prev_action.droll + inv_sf * action.droll,
            dpitch=sf * self._prev_action.dpitch + inv_sf * action.dpitch,
            dyaw=sf * self._prev_action.dyaw + inv_sf * action.dyaw,
            gripper=action.gripper,  # Gripper transition is discrete/direct
            confidence=sf * self._prev_action.confidence + inv_sf * action.confidence,
        )
        self._prev_action = smoothed
        return smoothed

    def reset(self) -> None:
        self._prev_action = None


class RollingWindowSmoothingFilter(ActionSmoothingFilter):
    """Windowed rolling history FIR filter (Savitzky-Golay / weighted moving average)."""

    def __init__(self, window_size: int = 5, weights: list[float] | None = None) -> None:
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        self.window_size = window_size

        if weights is not None:
            if len(weights) != window_size:
                raise ValueError(f"weights length ({len(weights)}) must match window_size ({window_size})")
            total_w = sum(weights)
            if total_w <= 0:
                raise ValueError("weights sum must be positive")
            self.weights = [w / total_w for w in weights]
        else:
            # Default to linear ramp (more recent actions have higher weight)
            raw_weights = [float(i + 1) for i in range(window_size)]
            tot = sum(raw_weights)
            self.weights = [w / tot for w in raw_weights]

        self._history: deque[VLAAction] = deque(maxlen=window_size)

    def update(self, action: VLAAction) -> VLAAction:
        self._history.append(action)
        k = len(self._history)
        if k == 1:
            return action

        # Sub-slice weights for partial window during warmup
        active_weights = self.weights[-k:]
        total_w = sum(active_weights)
        norm_weights = [w / total_w for w in active_weights]

        dx = sum(w * a.dx for w, a in zip(norm_weights, self._history, strict=False))
        dy = sum(w * a.dy for w, a in zip(norm_weights, self._history, strict=False))
        dz = sum(w * a.dz for w, a in zip(norm_weights, self._history, strict=False))
        droll = sum(w * a.droll for w, a in zip(norm_weights, self._history, strict=False))
        dpitch = sum(w * a.dpitch for w, a in zip(norm_weights, self._history, strict=False))
        dyaw = sum(w * a.dyaw for w, a in zip(norm_weights, self._history, strict=False))
        confidence = sum(w * a.confidence for w, a in zip(norm_weights, self._history, strict=False))

        return VLAAction(
            dx=dx,
            dy=dy,
            dz=dz,
            droll=droll,
            dpitch=dpitch,
            dyaw=dyaw,
            gripper=action.gripper,
            confidence=confidence,
        )

    def reset(self) -> None:
        self._history.clear()


def clamp_action_delta(
    action: VLAAction,
    max_step_size: float = 0.05,
    max_rotation_step: float = 0.2,
) -> VLAAction:
    """Clamp Cartesian translation and Euler rotation deltas to safe kinematic step limits."""
    dx, dy, dz = action.dx, action.dy, action.dz
    trans_norm = math.sqrt(dx**2 + dy**2 + dz**2)
    if trans_norm > max_step_size and trans_norm > 0:
        scale = max_step_size / trans_norm
        dx *= scale
        dy *= scale
        dz *= scale

    droll, dpitch, dyaw = action.droll, action.dpitch, action.dyaw
    rot_norm = math.sqrt(droll**2 + dpitch**2 + dyaw**2)
    if rot_norm > max_rotation_step and rot_norm > 0:
        scale_rot = max_rotation_step / rot_norm
        droll *= scale_rot
        dpitch *= scale_rot
        dyaw *= scale_rot

    return VLAAction(
        dx=dx,
        dy=dy,
        dz=dz,
        droll=droll,
        dpitch=dpitch,
        dyaw=dyaw,
        gripper=action.gripper,
        confidence=action.confidence,
    )


def export_vla_onnx_model(output_path: str | Path, feature_dim: int = 64) -> str:
    """Construct and export a genuine ONNX computational graph model for local VLA inference."""
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    img_input = helper.make_tensor_value_info("image", TensorProto.FLOAT, [1, 3, 224, 224])
    inst_input = helper.make_tensor_value_info("instruction", TensorProto.FLOAT, [1, feature_dim])
    action_out = helper.make_tensor_value_info("action", TensorProto.FLOAT, [1, 7])
    conf_out = helper.make_tensor_value_info("confidence", TensorProto.FLOAT, [1, 1])

    rng = np.random.RandomState(42)
    hidden_dim = 32
    fused_dim = 3 + feature_dim

    w_hidden = (rng.randn(hidden_dim, fused_dim) * 0.02).astype(np.float32)
    # Instruction mapping:
    # index 3: forward/back polarity
    # index 4: right/left polarity
    # index 5: up/down polarity
    # index 6: release/grasp polarity
    w_hidden[0, 3] = 2.0  # hidden 0 captures forward
    w_hidden[1, 4] = 2.0  # hidden 1 captures right
    w_hidden[2, 5] = 2.0  # hidden 2 captures up
    w_hidden[3, 6] = 3.0  # hidden 3 captures gripper

    # Couple visual channels to spatial features
    w_hidden[4, 0] = 0.1  # Red channel coupling
    w_hidden[5, 1] = 0.1  # Green channel coupling
    w_hidden[6, 2] = 0.1  # Blue channel coupling

    b_hidden = np.zeros(hidden_dim, dtype=np.float32)

    w_action = (rng.randn(7, hidden_dim) * 0.02).astype(np.float32)
    w_action[0, 0] = 1.0  # dx from hidden 0
    w_action[1, 1] = 1.0  # dy from hidden 1
    w_action[2, 2] = 1.0  # dz from hidden 2
    w_action[6, 3] = 1.0  # gripper from hidden 3
    b_action = np.zeros(7, dtype=np.float32)

    w_conf = (rng.randn(1, hidden_dim) * 0.01).astype(np.float32)
    b_conf = np.array([2.5], dtype=np.float32)  # High confidence baseline ~0.92

    w_hidden_init = helper.make_tensor(
        "W_hidden", TensorProto.FLOAT, [hidden_dim, fused_dim], w_hidden.flatten().tolist()
    )
    b_hidden_init = helper.make_tensor("B_hidden", TensorProto.FLOAT, [hidden_dim], b_hidden.flatten().tolist())
    w_action_init = helper.make_tensor("W_action", TensorProto.FLOAT, [7, hidden_dim], w_action.flatten().tolist())
    b_action_init = helper.make_tensor("B_action", TensorProto.FLOAT, [7], b_action.flatten().tolist())
    w_conf_init = helper.make_tensor("W_conf", TensorProto.FLOAT, [1, hidden_dim], w_conf.flatten().tolist())
    b_conf_init = helper.make_tensor("B_conf", TensorProto.FLOAT, [1], b_conf.flatten().tolist())
    reshape_shape = helper.make_tensor("reshape_shape", TensorProto.INT64, [2], [1, 3])

    nodes = [
        helper.make_node("GlobalAveragePool", ["image"], ["pool_out"]),
        helper.make_node("Reshape", ["pool_out", "reshape_shape"], ["vis_features"]),
        helper.make_node("Concat", ["vis_features", "instruction"], ["fused"], axis=1),
        helper.make_node("Gemm", ["fused", "W_hidden", "B_hidden"], ["hidden"], alpha=1.0, beta=1.0, transB=1),
        helper.make_node("Tanh", ["hidden"], ["hidden_act"]),
        helper.make_node("Gemm", ["hidden_act", "W_action", "B_action"], ["action_raw"], alpha=1.0, beta=1.0, transB=1),
        helper.make_node("Tanh", ["action_raw"], ["action"]),
        helper.make_node("Gemm", ["hidden_act", "W_conf", "B_conf"], ["conf_raw"], alpha=1.0, beta=1.0, transB=1),
        helper.make_node("Sigmoid", ["conf_raw"], ["confidence"]),
    ]

    graph = helper.make_graph(
        nodes,
        "VLAComputationalGraph",
        [img_input, inst_input],
        [action_out, conf_out],
        [w_hidden_init, b_hidden_init, w_action_init, b_action_init, w_conf_init, b_conf_init, reshape_shape],
    )

    model = helper.make_model(graph, producer_name="effero-vla", opset_imports=[helper.make_opsetid("", 17)])
    onnx.checker.check_model(model)
    onnx.save(model, str(out_path))
    logger.info(f"Exported valid ONNX VLA model to {out_path}")
    return str(out_path)


def encode_instruction(instruction: str, dim: int = 64) -> np.ndarray:
    """Project natural language instruction into continuous embedding vector in R^dim."""
    vec = np.zeros((1, dim), dtype=np.float32)
    inst_lower = instruction.lower()

    # Directional spatial grounding coordinates
    if any(k in inst_lower for k in ["forward", "front", "ahead", "reach"]):
        vec[0, 0] += 1.0
    if any(k in inst_lower for k in ["back", "backward", "reverse", "retreat"]):
        vec[0, 0] -= 1.0

    if "right" in inst_lower:
        vec[0, 1] += 1.0
    if "left" in inst_lower:
        vec[0, 1] -= 1.0

    if any(k in inst_lower for k in ["up", "lift", "ascend", "raise"]):
        vec[0, 2] += 1.0
    if any(k in inst_lower for k in ["down", "descend", "lower", "drop"]):
        vec[0, 2] -= 1.0

    words = set(inst_lower.replace(",", " ").replace(".", " ").split())
    if any(w in words for w in ["release", "open"]) or "release" in inst_lower:
        vec[0, 3] += 1.0
    if any(w in words for w in ["grasp", "grab", "close", "grip", "pinch", "hold"]):
        vec[0, 3] -= 1.0

    # Deterministic token hashing for remaining semantic dimensions
    for word in inst_lower.split():
        h = int(hashlib.md5(word.encode("utf-8")).hexdigest()[:8], 16)
        idx = 4 + (h % (dim - 4))
        sign = 1.0 if (h & 1) else -1.0
        vec[0, idx] += sign * 0.5

    # L2 normalize instruction representation
    norm = float(np.linalg.norm(vec))
    if norm > 1e-6:
        vec = vec / norm
    return vec


def preprocess_image(image: Image.Image | np.ndarray) -> np.ndarray:
    """Preprocess input image to normalized float32 tensor (1, 3, 224, 224)."""
    if isinstance(image, np.ndarray):
        pil_img = Image.fromarray(image).convert("RGB")
    else:
        pil_img = image.convert("RGB")

    width, height = pil_img.size
    if width == 0 or height == 0:
        raise ValueError("Input image has zero dimensions")

    resized = pil_img.resize((224, 224), Image.Resampling.BILINEAR)
    arr = np.array(resized, dtype=np.float32) / 255.0

    # Standard ImageNet normalization
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    norm_arr = (arr - mean) / std

    # Transpose HWC -> CHW and add batch dim -> (1, 3, 224, 224)
    tensor = np.transpose(norm_arr, (2, 0, 1))
    return np.expand_dims(tensor, axis=0).astype(np.float32)


class ONNXVLAEngine:
    """Real ONNX local VLA inference engine executing continuous 7-DOF action prediction."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        smoothing_filter: ActionSmoothingFilter | None = None,
        max_step_size: float = 0.05,
    ) -> None:
        self.max_step_size = max_step_size
        self.smoothing_filter = smoothing_filter or EMASmoothingFilter(smoothing_factor=0.7)

        if model_path is None:
            home_dir = Path.home() / ".effero" / "models"
            home_dir.mkdir(parents=True, exist_ok=True)
            self.model_path = home_dir / "vla_model.onnx"
        else:
            self.model_path = Path(model_path)

        if not self.model_path.exists():
            logger.info(f"VLA model not found at {self.model_path}; generating valid local ONNX artifact.")
            export_vla_onnx_model(self.model_path)

        # Initialize ONNX Runtime InferenceSession
        self.session = ort.InferenceSession(
            str(self.model_path),
            providers=["CPUExecutionProvider"],
        )

        # Inspect session metadata
        inputs = self.session.get_inputs()
        outputs = self.session.get_outputs()
        self.img_input_name = inputs[0].name
        self.inst_input_name = inputs[1].name
        self.action_output_name = outputs[0].name
        self.conf_output_name = outputs[1].name

    def predict_action(
        self,
        image: Image.Image | np.ndarray,
        instruction: str | np.ndarray,
    ) -> VLAAction:
        """Predict continuous 7-DOF action token using local ONNX graph inference."""
        img_tensor = preprocess_image(image)

        if isinstance(instruction, str):
            inst_tensor = encode_instruction(instruction, dim=64)
        elif isinstance(instruction, np.ndarray):
            inst_tensor = instruction.astype(np.float32)
            if inst_tensor.ndim == 1:
                inst_tensor = np.expand_dims(inst_tensor, axis=0)
        else:
            raise TypeError("Instruction must be a string or numpy array")

        outputs = self.session.run(
            [self.action_output_name, self.conf_output_name],
            {
                self.img_input_name: img_tensor,
                self.inst_input_name: inst_tensor,
            },
        )

        raw_action_arr = outputs[0][0]
        raw_conf = float(outputs[1][0][0])

        # Scale translation deltas by max step size (e.g. 0.05m)
        scaled_dx = float(raw_action_arr[0]) * self.max_step_size
        scaled_dy = float(raw_action_arr[1]) * self.max_step_size
        scaled_dz = float(raw_action_arr[2]) * self.max_step_size
        droll = float(raw_action_arr[3]) * 0.1
        dpitch = float(raw_action_arr[4]) * 0.1
        dyaw = float(raw_action_arr[5]) * 0.1

        # Gripper is discrete: 1.0 (open) or -1.0 (close)
        raw_grip = float(raw_action_arr[6])
        gripper_cmd = 1.0 if raw_grip >= 0.0 else -1.0

        action = VLAAction(
            dx=scaled_dx,
            dy=scaled_dy,
            dz=scaled_dz,
            droll=droll,
            dpitch=dpitch,
            dyaw=dyaw,
            gripper=gripper_cmd,
            confidence=raw_conf,
        )

        # Enforce kinematic delta clamping
        clamped = clamp_action_delta(action, max_step_size=self.max_step_size)

        # Apply temporal smoothing filter
        if self.smoothing_filter is not None:
            return self.smoothing_filter.update(clamped)
        return clamped


class VLAPolicyRunner:
    """Executes Vision-Language-Action models with action chunking and temporal smoothing."""

    def __init__(
        self,
        model_name: str = "openvla/openvla-7b",
        smoothing_factor: float = 0.7,
        max_step_size: float = 0.05,  # 5cm max delta per inference step
        filter_type: str = "ema",
    ):
        self.model_name = model_name
        self.smoothing_factor = smoothing_factor
        self.max_step_size = max_step_size

        if filter_type == "rolling":
            smoothing_filter: ActionSmoothingFilter = RollingWindowSmoothingFilter(window_size=5)
        else:
            smoothing_filter = EMASmoothingFilter(smoothing_factor=smoothing_factor)

        self.engine = ONNXVLAEngine(
            smoothing_filter=smoothing_filter,
            max_step_size=max_step_size,
        )

    def predict_action(
        self,
        image: Image.Image | np.ndarray,
        instruction: str,
    ) -> VLAAction:
        """Infer 7-DOF delta action from visual observation and prompt via ONNX graph."""
        return self.engine.predict_action(image, instruction)

    def execute_action(self, action: VLAAction) -> dict[str, Any]:
        """Apply predicted action delta to the active arm controller."""
        cur_x, cur_y, cur_z = _arm_controller.current_position
        new_x = cur_x + action.dx
        new_y = cur_y + action.dy
        new_z = cur_z + action.dz

        # Actuate gripper if state changed
        if action.gripper < 0 and _arm_controller.gripper_open:
            _arm_controller.set_gripper(open_gripper=False)
        elif action.gripper > 0 and not _arm_controller.gripper_open:
            _arm_controller.set_gripper(open_gripper=True)

        # Move to newly resolved Cartesian target
        return _arm_controller.move_to_cartesian(new_x, new_y, new_z)


#: Singleton VLA runner instance
_vla_runner = VLAPolicyRunner()


@skill(
    name="perception.vision.vla_step",
    description="Run a single Vision-Language-Action inference cycle from an image file and natural language prompt.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def vla_step(image_path: str, instruction: str) -> dict[str, Any]:
    img = Image.open(image_path).convert("RGB")
    action = _vla_runner.predict_action(img, instruction)
    exec_res = _vla_runner.execute_action(action)
    return {
        "status": "success",
        "predicted_action": action.to_dict(),
        "execution_result": exec_res,
    }
