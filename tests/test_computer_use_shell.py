"""Comprehensive tests for computer_use.shell skills."""

from __future__ import annotations

import sys

import pytest

from effero.skills.computer_use.shell import run


@pytest.mark.asyncio
async def test_shell_run_success() -> None:
    """Verify standard shell command execution and stdout capture."""
    cmd = f'"{sys.executable}" -c "print(\'effero_test_output\')"'
    res = await run(command=cmd)
    assert res["status"] == "success"
    assert res["returncode"] == 0
    assert "effero_test_output" in res["stdout"]
    assert res["stderr"] == ""


@pytest.mark.asyncio
async def test_shell_run_nonzero_exit() -> None:
    """Verify non-zero return code and stderr capture."""
    cmd = f'"{sys.executable}" -c "import sys; sys.stderr.write(\'error_msg\'); sys.exit(42)"'
    res = await run(command=cmd)
    assert res["status"] == "error"
    assert res["returncode"] == 42
    assert "error_msg" in res["stderr"]


@pytest.mark.asyncio
async def test_shell_run_timeout() -> None:
    """Verify command timing out is killed and returns structured error."""
    cmd = f'"{sys.executable}" -c "import time; time.sleep(5)"'
    res = await run(command=cmd, timeout=0.2)
    assert res["status"] == "error"
    assert res["returncode"] == -1
    assert "timed out after 0.2s" in res["error"]


@pytest.mark.asyncio
async def test_shell_run_blocks_dangerous_commands() -> None:
    """Verify dangerous/destructive command patterns are rejected before execution."""
    dangerous_commands = [
        "rm -rf /",
        "rm -rf /*",
        ":(){ :|:& };:",
        "mkfs.ext4 /dev/sda1",
        "format C:",
        "shutdown -h now",
        "reboot",
        "echo x > /dev/sda",
        "   ",
    ]
    for cmd in dangerous_commands:
        res = await run(command=cmd)
        assert res["status"] == "error"
        assert res["returncode"] == -1
        assert "safety policy" in res["error"].lower() or "not permitted" in res["error"].lower()


@pytest.mark.asyncio
async def test_shell_run_allowlist_enforcement() -> None:
    """Verify allowlist enforcement blocks commands outside authorized prefixes."""
    allowed = ["echo", "python"]
    # Disallowed command
    res_blocked = await run("whoami", allowed_commands=allowed)
    assert res_blocked["status"] == "error"
    assert "allowlist" in res_blocked["error"].lower()

    # Allowed command
    res_ok = await run(f'"{sys.executable}" -c "print(\'allowed\')"', allowed_commands=[f'"{sys.executable}"'])
    assert res_ok["status"] == "success"
    assert "allowed" in res_ok["stdout"]
