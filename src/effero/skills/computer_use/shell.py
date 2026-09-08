"""Shell execution skills."""

from __future__ import annotations

import asyncio

from effero.sdk.skill import SafetyClass, skill


@skill(
    name="computer_use.shell.run",
    description="Run a shell command",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def run(command: str, timeout: float = 60.0) -> dict:
    proc = await asyncio.create_subprocess_shell(
        command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "status": "success" if proc.returncode == 0 else "error",
            "returncode": proc.returncode,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
        }
    except TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return {
            "status": "error",
            "returncode": -1,
            "error": f"Command timed out after {timeout}s",
            "stdout": "",
            "stderr": f"Timeout expired ({timeout}s)",
        }
