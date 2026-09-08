"""Tests for Memory."""

from __future__ import annotations

import tempfile

from effero.core.memory.episodic import EpisodicMemory
from effero.core.memory.working import WorkingMemory


def test_add_and_get_messages() -> None:
    mem = WorkingMemory()
    mem.add_message("user", "hi")
    ctx = mem.get_context()
    assert len(ctx) == 1
    assert ctx[0]["role"] == "user"
    assert ctx[0]["content"] == "hi"


def test_max_messages_trim() -> None:
    mem = WorkingMemory(max_messages=3)
    mem.add_message("system", "sys prompt")
    mem.add_message("user", "msg 1")
    mem.add_message("user", "msg 2")
    mem.add_message("user", "msg 3")

    ctx = mem.get_context()
    assert len(ctx) == 3
    # System message should be preserved
    assert ctx[0]["role"] == "system"
    assert ctx[1]["content"] == "msg 2"
    assert ctx[2]["content"] == "msg 3"


def test_trim_large_message_burst() -> None:
    mem = WorkingMemory(max_messages=10)
    mem.add_message("system", "primary system prompt")
    for i in range(100):
        mem.add_message("user", f"query {i}")

    ctx = mem.get_context()
    assert len(ctx) == 10
    assert ctx[0]["role"] == "system"
    assert ctx[0]["content"] == "primary system prompt"
    # Last 9 user messages (91 to 99)
    assert ctx[1]["content"] == "query 91"
    assert ctx[-1]["content"] == "query 99"


def test_tool_result() -> None:
    mem = WorkingMemory()
    mem.add_tool_result("call-1", "test.skill", "result value")
    ctx = mem.get_context()
    assert len(ctx) == 1
    assert ctx[0]["role"] == "tool"
    assert ctx[0]["tool_call_id"] == "call-1"
    assert ctx[0]["name"] == "test.skill"


def test_clear() -> None:
    mem = WorkingMemory()
    mem.add_message("user", "hi")
    mem.clear()
    assert len(mem.get_context()) == 0


def test_episodic_record_and_load() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ep = EpisodicMemory(session_dir=tmpdir)
        ep.record("test_event", {"key": "value"})
        ep.record("test_event", {"key": "value2"})

        history = ep.load_history()
        assert len(history) == 2
        assert history[0]["type"] == "test_event"
        assert history[0]["data"]["key"] == "value"


def test_episodic_chunked_reverse_reading() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ep = EpisodicMemory(session_dir=tmpdir)
        # Write 500 events
        for i in range(500):
            ep.record("event", {"seq": i, "payload": "x" * 100})

        # Load only the latest 10 events
        history = ep.load_history(limit=10)
        assert len(history) == 10
        # Ensure chronological order is preserved (490 -> 499)
        assert history[0]["data"]["seq"] == 490
        assert history[-1]["data"]["seq"] == 499
