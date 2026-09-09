"""Shell execution skills."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

from effero.sdk.skill import SafetyClass, skill

# Patterns matching destructive, system-compromising, or denial-of-service commands
DANGEROUS_COMMAND_PATTERNS = [
    re.compile(r"\brm\s+-[rRfF]+\s+[/~*]"),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),  # fork bomb
    re.compile(r"\bmkfs(?:\.[a-z0-9]+)?\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=\S+\s+of=/dev/", re.IGNORECASE),
    re.compile(r"\bformat\s+[a-zA-Z]:", re.IGNORECASE),
    re.compile(r"\b(?:shutdown|reboot|poweroff|init\s+0)\b", re.IGNORECASE),
    re.compile(r">\s*/dev/(?:sd[a-z]|nvme[0-9])", re.IGNORECASE),
]


def is_command_safe(command: str, allowed_prefixes: list[str] | None = None) -> tuple[bool, str | None]:
    """Validate whether a shell command is permissible under safety policies."""
    stripped = command.strip()
    if not stripped:
        return False, "Empty or whitespace-only shell command is not permitted."

    # Check against destructive/system-wipe patterns
    for pattern in DANGEROUS_COMMAND_PATTERNS:
        if pattern.search(stripped):
            return (
                False,
                f"Dangerous command pattern detected: command matched blocked rule '{pattern.pattern}'",
            )

    # Check allowlist if configured via argument or environment
    env_allowlist = os.environ.get("EFFERO_SHELL_ALLOWLIST")
    effective_allowlist: list[str] = []
    if allowed_prefixes is not None:
        effective_allowlist.extend(allowed_prefixes)
    elif env_allowlist:
        effective_allowlist.extend([p.strip() for p in env_allowlist.split(",") if p.strip()])

    if effective_allowlist:
        matched = any(
            stripped == prefix or stripped.startswith(prefix + " ") or stripped.startswith(prefix + "\t")
            for prefix in effective_allowlist
        )
        if not matched:
            return (
                False,
                f"Command '{stripped[:50]}' does not match any allowed prefix in allowlist: {effective_allowlist}",
            )

    return True, None


@skill(
    name="computer_use.shell.run",
    description="Run a shell command",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def run(
    command: str,
    timeout: float = 60.0,
    allowed_commands: list[str] | None = None,
) -> dict[str, Any]:
    safe, violation = is_command_safe(command, allowed_prefixes=allowed_commands)
    if not safe:
        return {
            "status": "error",
            "returncode": -1,
            "error": f"Command rejected by safety policy: {violation}",
            "stdout": "",
            "stderr": "Safety violation: command blocked by shell guardrails",
        }

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
