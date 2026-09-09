"""Safety kernel client — talks to the Rust guardrail engine over TCP."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SafetyClient:
    """Async TCP client for the effero-safety-kernel.

    The safety kernel is an independent Rust process that evaluates
    proposed actions against a declarative policy before they reach hardware.
    Communication uses newline-delimited JSON over TCP.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 9400) -> None:
        self.host = host
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Connect to the safety kernel."""
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        self._connected = True
        logger.info(f"Connected to safety kernel at {self.host}:{self.port}")

    async def _send_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON request and read the JSON response under concurrency lock."""
        if not self._connected:
            await self.connect()

        async with self._lock:
            assert self._writer is not None
            assert self._reader is not None
            self._writer.write((json.dumps(request) + "\n").encode())
            await self._writer.drain()

            line = await self._reader.readline()
            if not line:
                self._connected = False
                raise ConnectionError("Safety kernel closed the connection")

            return json.loads(line.decode())

    async def check_action(self, skill_name: str, facts: dict[str, Any] | None = None) -> dict[str, Any]:
        """Check whether an action is allowed by the safety policy.

        Args:
            skill_name: The skill being invoked (e.g., 'iot.lights.toggle')
            facts: Optional dict of numeric/boolean facts for condition evaluation

        Returns:
            dict with 'decision' key: 'allow', 'require_approval', 'deny', or 'limit'
        """
        request = {"type": "evaluate", "skill": skill_name, "facts": facts or {}}
        result = await self._send_request(request)
        logger.debug(f"Safety check for '{skill_name}': {result}")
        return result

    async def send_heartbeat(self) -> dict[str, Any]:
        """Send a heartbeat to prevent the safety kernel watchdog from tripping."""
        request = {"type": "heartbeat"}
        return await self._send_request(request)

    async def get_status(self) -> dict[str, Any]:
        """Query safety kernel and watchdog status."""
        request = {"type": "status"}
        return await self._send_request(request)

    async def reset_watchdog(self) -> dict[str, Any]:
        """Reset the watchdog after a timeout trip."""
        request = {"type": "reset_watchdog"}
        return await self._send_request(request)

    async def close(self) -> None:
        """Close the connection."""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected
