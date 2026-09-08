"""Working memory module for Effero combining conversational context and time-series telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from effero.core.memory.timeseries import RollingWindowView, TimeSeriesRingBuffer


@dataclass
class WorkingMemory:
    max_messages: int = 100
    messages: list[dict[str, Any]] = field(default_factory=list)
    telemetry_streams: dict[str, TimeSeriesRingBuffer[Any]] = field(default_factory=dict)

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        msg = {"role": role, "content": content}
        msg.update(kwargs)
        self.messages.append(msg)
        self._trim()

    def add_tool_result(self, tool_call_id: str, name: str, result: str) -> None:
        msg = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": result,
        }
        self.messages.append(msg)
        self._trim()

    def record_metric(
        self,
        metric_name: str,
        value: Any,
        timestamp: float | None = None,
        max_capacity: int = 500,
    ) -> None:
        """Append a timestamped observation to named telemetry stream."""
        if metric_name not in self.telemetry_streams:
            self.telemetry_streams[metric_name] = TimeSeriesRingBuffer(max_capacity=max_capacity)
        self.telemetry_streams[metric_name].append(value, timestamp=timestamp)

    def get_latest_metric(self, metric_name: str) -> Any | None:
        """Retrieve most recent observation for a named telemetry metric."""
        stream = self.telemetry_streams.get(metric_name)
        if stream is None:
            return None
        pt = stream.get_latest()
        return pt.value if pt else None

    def get_metric_series(self, metric_name: str, last_seconds: float | None = None) -> list[tuple[float, Any]]:
        """Retrieve chronological (timestamp, value) observations for a named metric."""
        stream = self.telemetry_streams.get(metric_name)
        if stream is None:
            return []
        if last_seconds is not None:
            points = stream.get_last_n_seconds(last_seconds)
        else:
            points = list(stream._buffer)
        return [(pt.timestamp, pt.value) for pt in points]

    def interpolate_metric(self, metric_name: str, timestamp: float) -> float | None:
        """Estimate numeric scalar value at specific historical timestamp."""
        stream = self.telemetry_streams.get(metric_name)
        if stream is None:
            return None
        return stream.interpolate_numeric(timestamp)

    def rolling_metric(self, metric_name: str, seconds: float) -> RollingWindowView[Any] | None:
        """Return a rolling window statistical view for a named metric."""
        stream = self.telemetry_streams.get(metric_name)
        if stream is None:
            return None
        return stream.rolling(seconds)

    def get_context(self) -> list[dict[str, Any]]:
        return list(self.messages)

    def clear(self) -> None:
        self.messages.clear()
        for stream in self.telemetry_streams.values():
            stream.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "messages": self.messages,
            "telemetry_metrics": {k: len(v) for k, v in self.telemetry_streams.items()},
        }

    def _trim(self) -> None:
        if len(self.messages) <= self.max_messages:
            return

        system_msgs = [m for m in self.messages if m.get("role") == "system"]
        num_to_keep = self.max_messages - len(system_msgs)

        if num_to_keep <= 0:
            self.messages[:] = system_msgs
            return

        non_system_to_keep: list[dict[str, Any]] = []
        for m in reversed(self.messages):
            if m.get("role") != "system":
                non_system_to_keep.append(m)
                if len(non_system_to_keep) >= num_to_keep:
                    break

        non_system_to_keep.reverse()
        self.messages[:] = system_msgs + non_system_to_keep
