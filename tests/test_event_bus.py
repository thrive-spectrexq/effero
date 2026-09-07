"""Tests for the EventBus."""

from __future__ import annotations

import asyncio

import pytest

from effero.core.event_bus import Event, EventBus


@pytest.mark.asyncio
async def test_publish_and_subscribe() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("test.topic", handler)
    bus.publish(Event(topic="test.topic", data={"value": 1}, source="test"))

    # Allow dispatched tasks to run
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].data["value"] == 1


@pytest.mark.asyncio
async def test_wildcard_matching() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("perception.*", handler)
    bus.publish(Event(topic="perception.audio.utterance", data={"text": "hello"}, source="test"))
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].topic == "perception.audio.utterance"


@pytest.mark.asyncio
async def test_history_bounded() -> None:
    bus = EventBus(max_history=5)
    for i in range(10):
        bus.publish(Event(topic="test", data={"i": i}, source="test"))

    history = bus.get_history()
    assert len(history) == 5
    assert history[-1].data["i"] == 9


@pytest.mark.asyncio
async def test_no_subscribers() -> None:
    bus = EventBus()
    # Should not raise any error
    bus.publish(Event(topic="orphan", data={}, source="test"))
