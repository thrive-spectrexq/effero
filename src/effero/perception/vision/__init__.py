"""Vision perception module."""

from __future__ import annotations

from effero.perception.vision.detector import ColorBlobDetector, Detection, DetectionBackend
from effero.perception.vision.pipeline import VisionPipeline
from effero.perception.vision.stream import (
    Frame,
    FrameQueue,
    SyntheticFrameGenerator,
    VideoStreamIngestionLoop,
)
from effero.perception.vision.vla import (
    ActionSmoothingFilter,
    EMASmoothingFilter,
    ONNXVLAEngine,
    RollingWindowSmoothingFilter,
    VLAAction,
    VLAPolicyRunner,
    clamp_action_delta,
    export_vla_onnx_model,
    vla_step,
)

__all__ = [
    "DetectionBackend",
    "Detection",
    "ColorBlobDetector",
    "VisionPipeline",
    "Frame",
    "FrameQueue",
    "SyntheticFrameGenerator",
    "VideoStreamIngestionLoop",
    "ActionSmoothingFilter",
    "EMASmoothingFilter",
    "RollingWindowSmoothingFilter",
    "clamp_action_delta",
    "export_vla_onnx_model",
    "ONNXVLAEngine",
    "VLAAction",
    "VLAPolicyRunner",
    "vla_step",
]
