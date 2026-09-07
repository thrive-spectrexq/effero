"""Vision detection backends."""

from __future__ import annotations

import asyncio
import io
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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
        model = self._get_model()

        def _run_detect() -> list[Detection]:
            image = self._PIL_Image.open(io.BytesIO(image_data))
            results = model(image, conf=self.confidence_threshold, verbose=False)

            detections: list[Detection] = []
            for result in results:
                boxes = result.boxes
                for i in range(len(boxes)):
                    box = boxes[i]
                    cls_id = int(box.cls[0].item())
                    label = str(result.names[cls_id])
                    confidence = float(box.conf[0].item())
                    # xyxy format
                    x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
                    detections.append(Detection(label=label, confidence=confidence, bbox=(x1, y1, x2, y2)))
            return detections

        return await asyncio.to_thread(_run_detect)


class ColorBlobDetector(DetectionBackend):
    """Lightweight real computer-vision detector using color thresholding and bounding box extraction."""

    def __init__(self, target_color: str = "bright", threshold: int = 128) -> None:
        self.target_color = target_color
        self.threshold = max(0, min(255, threshold))

    async def detect(self, image_data: bytes) -> list[Detection]:
        def _analyze() -> list[Detection]:
            import numpy as np
            from PIL import Image

            try:
                img = Image.open(io.BytesIO(image_data)).convert("RGB")
            except Exception as e:
                logger.warning(f"Failed to decode image data for detection: {e}")
                return []

            arr = np.array(img, dtype=np.uint8)
            h, w, _ = arr.shape
            if h == 0 or w == 0:
                return []

            # Segment pixels based on color criterion
            if self.target_color == "red":
                mask = (
                    (arr[:, :, 0] > self.threshold)
                    & (arr[:, :, 0] > arr[:, :, 1] + 30)
                    & (arr[:, :, 0] > arr[:, :, 2] + 30)
                )
            elif self.target_color == "green":
                mask = (
                    (arr[:, :, 1] > self.threshold)
                    & (arr[:, :, 1] > arr[:, :, 0] + 30)
                    & (arr[:, :, 1] > arr[:, :, 2] + 30)
                )
            elif self.target_color == "blue":
                mask = (
                    (arr[:, :, 2] > self.threshold)
                    & (arr[:, :, 2] > arr[:, :, 0] + 30)
                    & (arr[:, :, 2] > arr[:, :, 1] + 30)
                )
            else:  # "bright" or general luminance
                luminance = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
                mask = luminance > self.threshold

            if not np.any(mask):
                return []

            # Find bounding box coordinates of segmented region
            ys, xs = np.where(mask)
            min_x, max_x = float(np.min(xs)), float(np.max(xs))
            min_y, max_y = float(np.min(ys)), float(np.max(ys))

            area = (max_x - min_x + 1) * (max_y - min_y + 1)
            total_pixels = float(h * w)
            fill_ratio = float(len(xs)) / total_pixels
            confidence = min(0.99, max(0.5, 0.5 + fill_ratio))

            return [
                Detection(
                    label=f"salient_{self.target_color}_object",
                    confidence=round(confidence, 3),
                    bbox=(min_x, min_y, max_x, max_y),
                    metadata={"pixel_count": int(len(xs)), "bounding_area": float(area)},
                )
            ]

        return await asyncio.to_thread(_analyze)
