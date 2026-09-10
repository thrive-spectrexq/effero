"""Deterministic sensor and telemetry replay system (`openpilot/tools/replay` pattern).

Allows recording live event bus telemetry and sensor observations to a compressed or
newline-delimited JSON stream (.efflog), and playing them back deterministically
with real-time pacing, speed factors, or stepping.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from effero.core.event_bus import Event, EventBus

logger = logging.getLogger(__name__)


class ReplayRecorder:
    """Subscribes to EventBus and logs all events with microsecond timestamps to `.efflog`."""

    def __init__(self, event_bus: EventBus, output_path: str | Path, topic_filter: str = "*") -> None:
        self.event_bus = event_bus
        self.output_path = Path(output_path)
        self.topic_filter = topic_filter
        self._file: Any = None
        self._count = 0
        self._is_recording = False

    def start(self) -> None:
        """Start recording events."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.output_path, "w", encoding="utf-8")
        self._count = 0
        self._is_recording = True

        async def _record_handler(event: Event) -> None:
            if not self._is_recording or self._file is None:
                return
            record = {
                "timestamp": event.timestamp,
                "topic": event.topic,
                "source": event.source,
                "data": event.data,
            }
            self._file.write(json.dumps(record) + "\n")
            self._file.flush()
            self._count += 1

        self.event_bus.subscribe(self.topic_filter, _record_handler)
        logger.info(f"Started recording to {self.output_path} with filter '{self.topic_filter}'")

    def stop(self) -> int:
        """Stop recording and close log file. Returns number of events recorded."""
        self._is_recording = False
        if self._file:
            self._file.close()
            self._file = None
        logger.info(f"Stopped recording. Wrote {self._count} events to {self.output_path}")
        return self._count


class ReplayPlayer:
    """Reads `.efflog` and injects messages into an EventBus in calibrated real-time."""

    def __init__(self, event_bus: EventBus, log_path: str | Path, speed: float = 1.0) -> None:
        self.event_bus = event_bus
        self.log_path = Path(log_path)
        self.speed = max(0.01, speed)
        self._is_playing = False
        self._records: list[dict[str, Any]] = []

    def load(self) -> int:
        """Load all entries into memory."""
        self._records.clear()
        if not self.log_path.exists():
            raise FileNotFoundError(f"Log file not found: {self.log_path}")

        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._records.append(json.loads(line))
        return len(self._records)

    async def play(self) -> int:
        """Play back recorded events through EventBus according to original timing."""
        if not self._records:
            self.load()

        if not self._records:
            return 0

        self._is_playing = True
        played = 0
        first_t = self._records[0]["timestamp"]
        start_mono = time.monotonic()

        for rec in self._records:
            if not self._is_playing:
                break

            # Calibrate delay relative to first timestamp
            event_offset = rec["timestamp"] - first_t
            target_elapsed = event_offset / self.speed
            current_elapsed = time.monotonic() - start_mono

            delay = target_elapsed - current_elapsed
            if delay > 0.001:
                await asyncio.sleep(delay)

            event = Event(
                topic=rec["topic"],
                data=rec["data"],
                source=f"replay:{rec.get('source', 'unknown')}",
                timestamp=time.time(),
            )
            self.event_bus.publish(event)
            played += 1

        self._is_playing = False
        return played

    def stop(self) -> None:
        """Cancel playback."""
        self._is_playing = False
