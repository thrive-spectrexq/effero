"""Async Event Bus for Effero internal pubsub."""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import re
import time
from collections import deque
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
    """High-performance asynchronous pub/sub event bus with compiled pattern routing."""

    def __init__(self, max_history: int = 1000):
        self._max_history = max_history
        self._history: deque[Event] = deque(maxlen=max_history)
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._exact_subscribers: dict[str, list[EventHandler]] = {}
        self._pattern_subscribers: list[tuple[str, re.Pattern[str], list[EventHandler]]] = []

    def subscribe(self, topic_pattern: str, handler: EventHandler) -> None:
        """Subscribe handler to exact topic or wildcard pattern."""
        if topic_pattern not in self._subscribers:
            self._subscribers[topic_pattern] = []
            if any(ch in topic_pattern for ch in ("*", "?", "[")):
                compiled = re.compile(fnmatch.translate(topic_pattern))
                self._pattern_subscribers.append((topic_pattern, compiled, self._subscribers[topic_pattern]))
            else:
                self._exact_subscribers[topic_pattern] = self._subscribers[topic_pattern]

        self._subscribers[topic_pattern].append(handler)

    def publish(self, event: Event) -> None:
        """Publish event and dispatch asynchronously to matched subscribers."""
        self._history.append(event)

        # Collect unique handlers across exact matches and wildcard patterns
        target_handlers: list[EventHandler] = []

        # 1. O(1) exact match lookup
        if event.topic in self._exact_subscribers:
            target_handlers.extend(self._exact_subscribers[event.topic])

        # 2. Pre-compiled regex evaluation for wildcard subscriptions
        for _pattern_str, regex, handlers in self._pattern_subscribers:
            if regex.match(event.topic):
                target_handlers.extend(handlers)

        if not target_handlers:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        for handler in target_handlers:
            loop.create_task(self._dispatch(handler, event))

    def get_history(self, topic_pattern: str = "*", limit: int = 100) -> list[Event]:
        """Retrieve recent chronological history filtered by topic."""
        if limit <= 0:
            return []

        if topic_pattern == "*":
            # Direct slice without pattern checks
            hist = list(self._history)
            return hist[-limit:]

        if not any(ch in topic_pattern for ch in ("*", "?", "[")):
            matches = [e for e in self._history if e.topic == topic_pattern]
            return matches[-limit:]

        regex = re.compile(fnmatch.translate(topic_pattern))
        matches = [e for e in self._history if regex.match(e.topic)]
        return matches[-limit:]

    async def _dispatch(self, handler: EventHandler, event: Event) -> None:
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"Error in event handler for topic {event.topic}: {e}")

    @staticmethod
    def _match_topic(pattern: str, topic: str) -> bool:
        return fnmatch.fnmatch(topic, pattern)
