"""Async Event Bus for Effero internal pubsub."""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Event:
    topic: str
    data: Any
    source: str
    timestamp: float = field(default_factory=time.time)


EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self, max_history: int = 1000):
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._history: list[Event] = []
        self._max_history = max_history

    def subscribe(self, topic_pattern: str, handler: EventHandler) -> None:
        if topic_pattern not in self._subscribers:
            self._subscribers[topic_pattern] = []
        self._subscribers[topic_pattern].append(handler)

    def publish(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        for pattern, handlers in self._subscribers.items():
            if self._match_topic(pattern, event.topic):
                for handler in handlers:
                    asyncio.create_task(self._dispatch(handler, event))

    def get_history(self, topic_pattern: str = "*", limit: int = 100) -> list[Event]:
        matches = [e for e in self._history if self._match_topic(topic_pattern, e.topic)]
        return matches[-limit:]

    async def _dispatch(self, handler: EventHandler, event: Event) -> None:
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"Error in event handler for topic {event.topic}: {e}")

    @staticmethod
    def _match_topic(pattern: str, topic: str) -> bool:
        return fnmatch.fnmatch(topic, pattern)
