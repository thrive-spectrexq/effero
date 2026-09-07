"""Sensor perception pipeline."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from effero.core.event_bus import Event, EventBus
from effero.perception.base import PerceptionPipeline

logger = logging.getLogger(__name__)


@dataclass
class SensorReading:
    sensor_id: str
    value: float | dict
    unit: str
    timestamp: datetime


class SensorBackend(ABC):
    """Base class for sensor backends."""

    @abstractmethod
    async def read(self) -> list[SensorReading]:
        """Read data from sensors."""
        ...


class MockSensor(SensorBackend):
    """Mock sensor for testing."""

    def __init__(self, fixed_readings: list[SensorReading] | None = None) -> None:
        self.fixed_readings = fixed_readings or []

    async def read(self) -> list[SensorReading]:
        return self.fixed_readings


class SensorPipeline(PerceptionPipeline):
    """Pipeline for reading sensor data periodically."""

    def __init__(
        self,
        event_bus: EventBus,
        sensor_backend: SensorBackend | None = None,
        poll_interval: float = 1.0,
    ) -> None:
        super().__init__(event_bus)
        self.sensor_backend = sensor_backend or MockSensor()
        self.poll_interval = poll_interval
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("SensorPipeline started.")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("SensorPipeline stopped.")

    async def _poll_loop(self) -> None:
        """Continuously poll sensors and publish readings."""
        while self._running:
            try:
                readings = await self.sensor_backend.read()
                for reading in readings:
                    event = Event(
                        topic="perception.sensor.reading",
                        data={
                            "sensor_id": reading.sensor_id,
                            "value": reading.value,
                            "unit": reading.unit,
                        },
                        timestamp=reading.timestamp,
                        source="sensor_pipeline",
                    )
                    await self.event_bus.publish(event)
            except Exception as e:
                logger.error(f"Error reading sensors: {e}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    @classmethod
    def from_config(cls, config: dict[str, Any], event_bus: EventBus) -> SensorPipeline:
        """Create a SensorPipeline from configuration."""
        poll_interval = config.get("poll_interval", 1.0)

        # Add support for other sensor backends as needed
        sensor = MockSensor()

        return cls(event_bus=event_bus, sensor_backend=sensor, poll_interval=poll_interval)
