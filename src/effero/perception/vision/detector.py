"""Vision detection backends."""

from __future__ import annotations

import io
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: tuple[float, float, float, float]
    metadata: dict = field(default_factory=dict)


class DetectionBackend(ABC):
    """Base class for detection backends."""

    @abstractmethod
    async def detect(self, image_data: bytes) -> list[Detection]:
        """Detect objects in image data."""
        ...


class YOLODetector(DetectionBackend):
    """Object detection using YOLO via ultralytics."""

    def __init__(self, model_name: str = "yolov9c", confidence_threshold: float = 0.5) -> None:
        try:
            import ultralytics
            from PIL import Image
        except ImportError:
            raise ImportError("Please install ultralytics and Pillow: pip install ultralytics pillow")

        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self._model = None
        self._ultralytics = ultralytics
        self._PIL_Image = Image

    def _get_model(self):
        if self._model is None:
            self._model = self._ultralytics.YOLO(f"{self.model_name}.pt")
        return self._model

    async def detect(self, image_data: bytes) -> list[Detection]:
        import asyncio

        model = self._get_model()

        def _run_detect():
            image = self._PIL_Image.open(io.BytesIO(image_data))
            results = model(image, conf=self.confidence_threshold, verbose=False)

            detections = []
            for result in results:
                boxes = result.boxes
                for i in range(len(boxes)):
                    box = boxes[i]
                    cls_id = int(box.cls[0].item())
                    label = result.names[cls_id]
                    confidence = float(box.conf[0].item())
                    # xyxy format
                    x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
                    detections.append(Detection(label=label, confidence=confidence, bbox=(x1, y1, x2, y2)))
            return detections

        return await asyncio.to_thread(_run_detect)


class MockDetector(DetectionBackend):
    """Mock detector for testing."""

    def __init__(self, fixed_detections: list[Detection] | None = None) -> None:
        self.fixed_detections = fixed_detections or []

    async def detect(self, image_data: bytes) -> list[Detection]:
        return self.fixed_detections
