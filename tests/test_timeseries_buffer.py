"""Tests for TimeSeriesRingBuffer and WorkingMemory timeseries integration."""

import time

import pytest

from effero.core.memory.timeseries import TimeSeriesRingBuffer
from effero.core.memory.working import WorkingMemory


def test_timeseries_capacity_eviction():
    buf = TimeSeriesRingBuffer[float](max_capacity=3)
    t0 = 100.0

    buf.append(1.0, timestamp=t0)
    buf.append(2.0, timestamp=t0 + 1.0)
    buf.append(3.0, timestamp=t0 + 2.0)
    assert len(buf) == 3

    # Add 4th point, 1st point should be evicted
    buf.append(4.0, timestamp=t0 + 3.0)
    assert len(buf) == 3
    assert buf.get_latest().value == 4.0

    pts = buf.get_window(start_timestamp=t0, end_timestamp=t0 + 10.0)
    assert [p.value for p in pts] == [2.0, 3.0, 4.0]


def test_timeseries_interpolation():
    buf = TimeSeriesRingBuffer[float](max_capacity=10)
    t0 = 1000.0
    buf.append(10.0, timestamp=t0)
    buf.append(20.0, timestamp=t0 + 10.0)

    # Midpoint interpolation
    mid = buf.interpolate_numeric(t0 + 5.0)
    assert mid == pytest.approx(15.0)

    # Quarter interpolation
    q = buf.interpolate_numeric(t0 + 2.5)
    assert q == pytest.approx(12.5)

    # Left clamp
    assert buf.interpolate_numeric(t0 - 5.0) == pytest.approx(10.0)

    # Right clamp
    assert buf.interpolate_numeric(t0 + 15.0) == pytest.approx(20.0)


def test_timeseries_window_queries():
    buf = TimeSeriesRingBuffer[str](max_capacity=10)
    t0 = 500.0
    buf.append("a", timestamp=t0)
    buf.append("b", timestamp=t0 + 5.0)
    buf.append("c", timestamp=t0 + 10.0)

    # Sliced query
    window = buf.get_window(start_timestamp=t0 + 2.0, end_timestamp=t0 + 8.0)
    assert len(window) == 1
    assert window[0].value == "b"

    # Non-numeric interpolation returns None
    assert buf.interpolate_numeric(t0 + 5.0) is None


def test_working_memory_telemetry_integration():
    mem = WorkingMemory()
    t_now = time.time()

    mem.record_metric("battery_pct", 98.0, timestamp=t_now)
    mem.record_metric("battery_pct", 96.0, timestamp=t_now + 10.0)

    assert mem.get_latest_metric("battery_pct") == 96.0
    assert mem.get_latest_metric("unknown_metric") is None

    # Series retrieval
    series = mem.get_metric_series("battery_pct")
    assert len(series) == 2
    assert series[0][1] == 98.0
    assert series[1][1] == 96.0

    # Interpolation
    val = mem.interpolate_metric("battery_pct", t_now + 5.0)
    assert val == pytest.approx(97.0)

    # Memory dictionary representation
    dump = mem.to_dict()
    assert "telemetry_metrics" in dump
    assert dump["telemetry_metrics"]["battery_pct"] == 2

    # Clear memory clears telemetry
    mem.clear()
    assert len(mem.get_metric_series("battery_pct")) == 0


def test_timeseries_rolling_statistics():
    buf = TimeSeriesRingBuffer[float](max_capacity=50)
    t_now = time.time()

    # Append 5 samples over 4 seconds: 10, 20, 30, 40, 50
    for i, v in enumerate([10.0, 20.0, 30.0, 40.0, 50.0]):
        buf.append(v, timestamp=t_now - 4.0 + i * 1.0)

    # Rolling window of trailing 5 seconds covers all 5 points
    roll = buf.rolling(seconds=5.0)
    assert roll.count() == 5
    assert roll.mean() == pytest.approx(30.0)
    assert roll.min() == pytest.approx(10.0)
    assert roll.max() == pytest.approx(50.0)
    assert roll.std() == pytest.approx(15.8113883, rel=1e-4)

    # Rate of change: (50 - 10) / 4s = 10.0 units/sec
    assert roll.rate_of_change() == pytest.approx(10.0)

    # Rolling window of trailing 2.5 seconds covers last 3 points: 30, 40, 50
    roll_short = buf.rolling(seconds=2.5)
    assert roll_short.count() == 3
    assert roll_short.mean() == pytest.approx(40.0)


def test_working_memory_rolling_metric():
    mem = WorkingMemory()
    t_now = time.time()
    mem.record_metric("cpu_temp", 40.0, timestamp=t_now - 2.0)
    mem.record_metric("cpu_temp", 50.0, timestamp=t_now - 1.0)
    mem.record_metric("cpu_temp", 60.0, timestamp=t_now)

    view = mem.rolling_metric("cpu_temp", seconds=5.0)
    assert view is not None
    assert view.mean() == pytest.approx(50.0)
    assert view.max() == pytest.approx(60.0)

    assert mem.rolling_metric("nonexistent", seconds=5.0) is None
