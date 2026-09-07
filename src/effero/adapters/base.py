"""Base interface for device adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DeviceAdapter(ABC):
    """Base class for all device adapters in the Device Abstraction Layer."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def execute(self, command: str, params: dict[str, Any]) -> Any: ...

    @abstractmethod
    async def read_state(self) -> dict[str, Any]: ...
