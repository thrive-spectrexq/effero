"""Sensor perception pipeline."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import psutil

from effero.core.event_bus import Event, EventBus
from effero.perception.base import PerceptionPipeline

logger = logging.getLogger(__name__)


@dataclass
class SensorReading:
    sensor_id: str
    value: float | dict
    unit: str
    timestamp: float = field(default_factory=time.time)


class SensorBackend(ABC):
    """Base class for sensor backends."""

    @abstractmethod
    async def read(self) -> list[SensorReading]:
        """Read data from sensors."""
        ...


class SystemMetricsSensor(SensorBackend):
    """Reads real physical and host system metrics (CPU, RAM, Disk telemetry)."""

    def __init__(self) -> None:
        # Initialize CPU measurement
        psutil.cpu_percent(interval=None)

    async def read(self) -> list[SensorReading]:
        def _collect() -> list[SensorReading]:
            now = time.time()
            cpu_val = float(psutil.cpu_percent(interval=None))
            mem = psutil.virtual_memory()
            mem_val = float(mem.percent)

            # Check primary partition for disk usage
            root_path = "C:\\" if sys.platform.startswith("win") else "/"
            try:
                disk = psutil.disk_usage(root_path)
                disk_val = float(disk.percent)
            except Exception:
                disk_val = 0.0

            return [
                SensorReading(
                    sensor_id="system.cpu.percent",
                    value=cpu_val,
                    unit="%",
                    timestamp=now,
                ),
                SensorReading(
                    sensor_id="system.memory.percent",
                    value=mem_val,
                    unit="%",
                    timestamp=now,
                ),
                SensorReading(
                    sensor_id="system.disk.percent",
                    value=disk_val,
                    unit="%",
                    timestamp=now,
                ),
            ]

        return await asyncio.to_thread(_collect)


class SensorPipeline(PerceptionPipeline):
    """Pipeline for reading sensor data periodically."""

    def __init__(
        self,
        event_bus: EventBus,
        sensor_backend: SensorBackend | None = None,
        poll_interval: float = 1.0,
    ) -> None:
        super().__init__(event_bus)
        self.sensor_backend: SensorBackend = sensor_backend or SystemMetricsSensor()
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
                    self.event_bus.publish(event)
            except Exception as e:
                logger.error(f"Error reading sensors: {e}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    @classmethod
    def from_config(cls, config: dict[str, Any], event_bus: EventBus) -> SensorPipeline:
        """Create a SensorPipeline from configuration."""
        poll_interval = config.get("poll_interval", 1.0)
        sensor: SensorBackend = SystemMetricsSensor()
        return cls(event_bus=event_bus, sensor_backend=sensor, poll_interval=poll_interval)
