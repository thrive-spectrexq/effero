"""Tests for deterministic replay recorder and player."""

import asyncio
from pathlib import Path

import pytest

from effero.core.event_bus import Event, EventBus
from effero.core.replay import ReplayPlayer, ReplayRecorder


@pytest.mark.asyncio
async def test_replay_record_and_play(tmp_path: Path) -> None:
    event_bus = EventBus()
    log_file = tmp_path / "test_session.efflog"

    recorder = ReplayRecorder(event_bus=event_bus, output_path=log_file, topic_filter="robotics.*")
    recorder.start()

    # Publish events
    e1 = Event(topic="robotics.pose", data={"x": 1.0, "y": 2.0}, source="nav")
    e2 = Event(topic="robotics.joint", data={"arm": [0.1, 0.2]}, source="arm")
    e3 = Event(topic="iot.lights", data={"on": True}, source="light")  # Should be filtered out

    event_bus.publish(e1)
    event_bus.publish(e2)
    event_bus.publish(e3)

    await asyncio.sleep(0.05)
    count = recorder.stop()
    assert count == 2
    assert log_file.exists()

    # Now playback on fresh event bus
    playback_bus = EventBus()
    received_events: list[Event] = []

    async def on_playback(event: Event) -> None:
        received_events.append(event)

    playback_bus.subscribe("*", on_playback)

    player = ReplayPlayer(event_bus=playback_bus, log_path=log_file, speed=10.0)
    entries = player.load()
    assert entries == 2

    played = await player.play()
    assert played == 2
    await asyncio.sleep(0.05)

    assert len(received_events) == 2
    assert received_events[0].topic == "robotics.pose"
    assert received_events[0].data == {"x": 1.0, "y": 2.0}
    assert received_events[0].source == "replay:nav"

    assert received_events[1].topic == "robotics.joint"
    assert received_events[1].data == {"arm": [0.1, 0.2]}
