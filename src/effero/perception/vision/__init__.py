"""Vision perception module."""
from __future__ import annotations

from effero.perception.vision.detector import Detection, DetectionBackend
from effero.perception.vision.pipeline import VisionPipeline

__all__ = [
    "DetectionBackend",
    "Detection",
    "VisionPipeline",
]
