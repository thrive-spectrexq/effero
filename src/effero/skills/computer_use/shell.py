"""Shell execution skills."""
from __future__ import annotations

import asyncio

from effero.sdk.skill import SafetyClass, skill


@skill(
    name="computer_use.shell.run",
    description="Run a shell command",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def run(command: str) -> dict:
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return {
        "status": "success" if proc.returncode == 0 else "error",
        "returncode": proc.returncode,
        "stdout": stdout.decode(errors='replace'),
        "stderr": stderr.decode(errors='replace')
    }
