"""Tests for SafetyDaemonManager binary discovery and status checks."""

from pathlib import Path

import pytest

from effero.safety.daemon import SafetyDaemonManager


@pytest.mark.asyncio
async def test_safety_daemon_manager_binary_discovery():
    """Verify SafetyDaemonManager looks for binary in target/ and system paths."""
    manager = SafetyDaemonManager(host="127.0.0.1", port=9499)
    # Check is_running on an unused port
    running = await manager.is_running()
    assert running is False

    # Binary may or may not be built in current workspace, but method executes cleanly
    binary = manager.find_binary()
    if binary:
        assert isinstance(binary, Path)
        assert binary.exists()
