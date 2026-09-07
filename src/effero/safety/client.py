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

    async def connect(self) -> None:
        """Connect to the safety kernel."""
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        self._connected = True
        logger.info(f"Connected to safety kernel at {self.host}:{self.port}")

    async def check_action(self, skill_name: str, facts: dict[str, Any] | None = None) -> dict:
        """Check whether an action is allowed by the safety policy.

        Args:
            skill_name: The skill being invoked (e.g., 'iot.lights.toggle')
            facts: Optional dict of numeric/boolean facts for condition evaluation

        Returns:
            dict with 'decision' key: 'allow', 'require_approval', 'deny', or 'limit'
        """
        if not self._connected:
            await self.connect()

        request = {"skill": skill_name, "facts": facts or {}}
        assert self._writer is not None
        assert self._reader is not None
        self._writer.write((json.dumps(request) + "\n").encode())
        await self._writer.drain()

        line = await self._reader.readline()
        if not line:
            raise ConnectionError("Safety kernel closed the connection")

        result = json.loads(line.decode())
        logger.debug(f"Safety check for '{skill_name}': {result}")
        return result

    async def close(self) -> None:
        """Close the connection."""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected
