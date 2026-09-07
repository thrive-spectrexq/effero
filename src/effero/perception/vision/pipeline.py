"""Vision perception pipeline."""

from __future__ import annotations

import logging
import time
from typing import Any

from effero.core.event_bus import Event, EventBus
from effero.perception.base import PerceptionPipeline
from effero.perception.vision.detector import ColorBlobDetector, Detection, DetectionBackend

logger = logging.getLogger(__name__)


class VisionPipeline(PerceptionPipeline):
    """Pipeline for processing visual input."""

    def __init__(self, event_bus: EventBus, detector_backend: DetectionBackend | None = None) -> None:
        super().__init__(event_bus)
        self.detector_backend: DetectionBackend = detector_backend or ColorBlobDetector()

    async def start(self) -> None:
        self._running = True
        logger.info("VisionPipeline started.")

    async def stop(self) -> None:
        self._running = False
        logger.info("VisionPipeline stopped.")

    async def process_frame(self, image_data: bytes) -> list[Detection]:
        """Process an image frame, detect objects, and publish an event."""
        detections = await self.detector_backend.detect(image_data)

        event = Event(
            topic="perception.vision.detection",
            data={
                "detections": [
                    {
                        "label": d.label,
                        "confidence": d.confidence,
                        "bbox": d.bbox,
                        "metadata": d.metadata,
                    }
                    for d in detections
                ]
            },
            timestamp=time.time(),
            source="vision_pipeline",
        )
        self.event_bus.publish(event)

        return detections

    @classmethod
    def from_config(cls, config: dict[str, Any], event_bus: EventBus) -> VisionPipeline:
        """Create a VisionPipeline from configuration."""
        detector_config = config.get("detector", {})
        detector_type = detector_config.get("type", "blob")

        detector: DetectionBackend
        if detector_type == "yolo":
            from effero.perception.vision.detector import YOLODetector

            detector = YOLODetector(
                model_name=detector_config.get("model_name", "yolov9c"),
                confidence_threshold=detector_config.get("confidence_threshold", 0.5),
            )
        else:
            detector = ColorBlobDetector(
                target_color=detector_config.get("target_color", "bright"),
                threshold=detector_config.get("threshold", 128),
            )

        return cls(event_bus=event_bus, detector_backend=detector)
