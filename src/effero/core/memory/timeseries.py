"""Time-series ring buffer with temporal slicing, numerical interpolation, and rolling statistics.

Inspired by Pandas Series, rolling window operations, and NumPy numerical processing.
"""

from __future__ import annotations

import bisect
import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class TimePoint(Generic[T]):
    """A timestamped data point."""

    timestamp: float
    value: T


class RollingWindowView(Generic[T]):
    """View of observations within a temporal window with Pandas-style summary statistics."""

    def __init__(self, points: list[TimePoint[T]]) -> None:
        self.points = points

    def count(self) -> int:
        """Total number of observations in window."""
        return len(self.points)

    def values(self) -> list[T]:
        """Raw list of values in chronological order."""
        return [pt.value for pt in self.points]

    def _numeric_values(self) -> list[float]:
        return [float(pt.value) for pt in self.points if isinstance(pt.value, (int, float))]

    def mean(self) -> float | None:
        """Arithmetic mean of numeric values in window."""
        vals = self._numeric_values()
        if not vals:
            return None
        return sum(vals) / len(vals)

    def min(self) -> float | None:
        """Minimum numeric value in window."""
        vals = self._numeric_values()
        if not vals:
            return None
        return min(vals)

    def max(self) -> float | None:
        """Maximum numeric value in window."""
        vals = self._numeric_values()
        if not vals:
            return None
        return max(vals)

    def std(self) -> float | None:
        """Sample standard deviation of numeric values in window."""
        vals = self._numeric_values()
        if not vals:
            return None
        if len(vals) < 2:
            return 0.0
        avg = sum(vals) / len(vals)
        variance = sum((v - avg) ** 2 for v in vals) / (len(vals) - 1)
        return math.sqrt(variance)

    def rate_of_change(self) -> float | None:
        """Rate of change across window: (value_end - value_start) / (time_end - time_start).

        Returns units of value per second.
        """
        numeric_pts = [pt for pt in self.points if isinstance(pt.value, (int, float))]
        if len(numeric_pts) < 2:
            return None
        p_start, p_end = numeric_pts[0], numeric_pts[-1]
        dt = p_end.timestamp - p_start.timestamp
        if dt <= 1e-9:
            return 0.0
        v_start = float(p_start.value)  # type: ignore[arg-type]
        v_end = float(p_end.value)  # type: ignore[arg-type]
        return float((v_end - v_start) / dt)


class TimeSeriesRingBuffer(Generic[T]):
    """Fixed-capacity chronological ring buffer with temporal range queries and interpolation."""

    def __init__(self, max_capacity: int = 1000) -> None:
        if max_capacity <= 0:
            raise ValueError("max_capacity must be strictly positive")
        self.max_capacity = max_capacity
        self._buffer: deque[TimePoint[T]] = deque(maxlen=max_capacity)

    def append(self, value: T, timestamp: float | None = None) -> None:
        """Record a new observation with monotonic or current system timestamp."""
        ts = time.time() if timestamp is None else float(timestamp)
        self._buffer.append(TimePoint(timestamp=ts, value=value))

    def get_latest(self) -> TimePoint[T] | None:
        """Return the most recent recorded observation."""
        if not self._buffer:
            return None
        return self._buffer[-1]

    def get_window(self, start_timestamp: float, end_timestamp: float | None = None) -> list[TimePoint[T]]:
        """Return all observations recorded within [start_timestamp, end_timestamp]."""
        end_ts = time.time() if end_timestamp is None else end_timestamp
        if start_timestamp > end_ts:
            return []

        return [pt for pt in self._buffer if start_timestamp <= pt.timestamp <= end_ts]

    def get_last_n_seconds(self, seconds: float) -> list[TimePoint[T]]:
        """Return observations recorded within the trailing duration."""
        now = time.time()
        return self.get_window(start_timestamp=now - seconds, end_timestamp=now)

    def rolling(self, seconds: float) -> RollingWindowView[T]:
        """Produce a rolling temporal window covering trailing duration in seconds."""
        points = self.get_last_n_seconds(seconds)
        return RollingWindowView(points)

    def interpolate_numeric(self, timestamp: float) -> float | None:
        """Estimate numeric scalar value at exact timestamp via linear interpolation.

        Only valid when stored values are numeric (float/int).
        """
        if not self._buffer:
            return None

        # If timestamp is before earliest point or after latest point, clamp to boundary
        if timestamp <= self._buffer[0].timestamp:
            val = self._buffer[0].value
            return float(val) if isinstance(val, (int, float)) else None

        if timestamp >= self._buffer[-1].timestamp:
            val = self._buffer[-1].value
            return float(val) if isinstance(val, (int, float)) else None

        # Binary search for interval [t_i, t_{i+1}]
        timestamps = [pt.timestamp for pt in self._buffer]
        idx = bisect.bisect_right(timestamps, timestamp)
        p0 = self._buffer[idx - 1]
        p1 = self._buffer[idx]

        v0, v1 = p0.value, p1.value
        if not (isinstance(v0, (int, float)) and isinstance(v1, (int, float))):
            return None

        dt = p1.timestamp - p0.timestamp
        f0 = float(v0)  # type: ignore[arg-type]
        f1 = float(v1)  # type: ignore[arg-type]
        if dt <= 1e-9:
            return f0

        alpha = (timestamp - p0.timestamp) / dt
        return float(f0 + alpha * (f1 - f0))

    def clear(self) -> None:
        """Clear all buffered data points."""
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)

    def to_dict(self) -> dict[str, Any]:
        """Serialize buffer metadata and data points."""
        return {
            "capacity": self.max_capacity,
            "count": len(self._buffer),
            "points": [{"timestamp": pt.timestamp, "value": pt.value} for pt in self._buffer],
        }
