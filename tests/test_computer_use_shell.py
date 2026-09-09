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
