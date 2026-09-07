"""Serial and GPIO adapter implementation."""
from __future__ import annotations

import json
import logging
from typing import Any

from effero.adapters.base import DeviceAdapter

logger = logging.getLogger(__name__)

try:
    import serial_asyncio
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


class SerialAdapter(DeviceAdapter):
    """Serial port adapter for communicating with microcontrollers and GPIO bridges."""

    def __init__(self, port: str, baudrate: int = 9600) -> None:
        self.port = port
        self.baudrate = baudrate
        self._reader: Any = None
        self._writer: Any = None
        self._last_state: dict[str, Any] = {}

    async def connect(self) -> None:
        if not HAS_SERIAL:
            logger.warning("pyserial-asyncio not installed — using mock serial adapter")
            return
            
        self._reader, self._writer = await serial_asyncio.open_serial_connection(url=self.port, baudrate=self.baudrate)
        logger.info(f"Connected to serial port {self.port} at {self.baudrate} baud")

    async def disconnect(self) -> None:
        if self._writer:
            self._writer.close()
            self._reader = None
            self._writer = None
            logger.info(f"Disconnected from serial port {self.port}")

    async def execute(self, command: str, params: dict[str, Any]) -> Any:
        msg = {"command": command, "params": params}
        
        if self._writer and self._reader:
            self._writer.write((json.dumps(msg) + "\n").encode())
            # In a real implementation, we'd want to handle timeouts and reading better
            line = await self._reader.readline()
            try:
                response = json.loads(line.decode().strip())
                self._last_state.update(response)
                return response
            except json.JSONDecodeError:
                return {"status": "error", "raw": line.decode().strip()}
        else:
            logger.info(f"[Mock Serial Tx] {self.port}: {msg}")
            self._last_state[command] = params
            return {"status": "mock", "command": command}

    async def read_state(self) -> dict[str, Any]:
        return self._last_state


class MockSerialAdapter(SerialAdapter):
    """Mock Serial Adapter for testing."""

    async def connect(self) -> None:
        logger.info(f"Mock connected to serial port {self.port} at {self.baudrate} baud")

    async def disconnect(self) -> None:
        logger.info(f"Mock disconnected from serial port {self.port}")

    async def execute(self, command: str, params: dict[str, Any]) -> Any:
        msg = {"command": command, "params": params}
        logger.info(f"[Mock Serial Tx] {self.port}: {msg}")
        self._last_state[command] = params
        return {"status": "mock", "command": command, "params": params}
