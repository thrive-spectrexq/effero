"""Tests for community skills."""

from __future__ import annotations

from effero.skills.community.system_info import get_system_overview


def test_community_system_overview_telemetry() -> None:
    data = get_system_overview()

    assert "os" in data
    assert "system" in data["os"]
    assert "cpu" in data
    assert "usage_percent" in data["cpu"]
    assert "memory" in data
    assert "total_gb" in data["memory"]
    assert data["memory"]["total_gb"] > 0
    assert "disk" in data
    assert "total_gb" in data["disk"]
    assert "uptime" in data
    assert data["uptime"]["uptime_seconds"] > 0
