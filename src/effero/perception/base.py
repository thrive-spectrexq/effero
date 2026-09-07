"""Base interface for perception pipelines."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class PerceptionPipeline(ABC):
    """Base class for all perception pipelines."""

    def __init__(self, event_bus) -> None:
        self.event_bus = event_bus
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """Start the perception pipeline."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the perception pipeline."""
        ...

    @property
    def running(self) -> bool:
        return self._running
