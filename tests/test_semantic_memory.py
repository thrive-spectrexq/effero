"""Tests for Semantic Vector Memory."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from effero.core.memory.semantic import (
    LightweightTFIDFEmbedding,
    SemanticMemory,
    cosine_similarity,
)


def test_cosine_similarity() -> None:
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert cosine_similarity(v1, v2) == 1.0

    v3 = [0.0, 1.0, 0.0]
    assert cosine_similarity(v1, v3) == 0.0


def test_embedder_normalization() -> None:
    embedder = LightweightTFIDFEmbedding(dim=64)
    v = embedder.embed("robot arm pickup object")
    assert len(v) == 64
    norm_sq = sum(x * x for x in v)
    assert pytest.approx(norm_sq, abs=1e-5) == 1.0


def test_semantic_memory_store_and_search() -> None:
    mem = SemanticMemory()
    mem.store("Living room ceiling lights toggle command", {"category": "iot"})
    mem.store("Kitchen oven temperature setting", {"category": "iot"})
    mem.store("Move robot arm to position XYZ", {"category": "robotics"})
    mem.store("List files in user home directory", {"category": "computer_use"})

    assert mem.count() == 4

    # Search for lights
    results = mem.search("turn on the light in the living room", top_k=2)
    assert len(results) > 0
    assert "lights" in results[0].text.lower()
    assert results[0].score > 0.0

    # Search for robotics
    robot_results = mem.search("robot arm joint motion", top_k=1)
    assert len(robot_results) == 1
    assert "robot arm" in robot_results[0].text


def test_semantic_memory_metadata_filter() -> None:
    mem = SemanticMemory()
    mem.store("Light 1", {"room": "living_room"})
    mem.store("Light 2", {"room": "bedroom"})

    results = mem.search("Light", filter_metadata={"room": "bedroom"})
    assert len(results) == 1
    assert results[0].text == "Light 2"


def test_semantic_memory_persistence() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "semantic_index.json"
        mem1 = SemanticMemory(persistence_path=db_path)
        mem1.store("Critical safety limit: max torque is 50Nm", {"type": "safety_rule"})
        mem1.store("System shutdown command: sys_halt", {"type": "system"})
        assert mem1.count() == 2

        # Verify file was written
        assert db_path.exists()

        # Load in a fresh instance
        mem2 = SemanticMemory(persistence_path=db_path)
        assert mem2.count() == 2
        results = mem2.search("safety limit torque", top_k=1)
        assert len(results) == 1
        assert "50Nm" in results[0].text


def test_delete_and_clear() -> None:
    mem = SemanticMemory()
    id1 = mem.store("Note 1")
    mem.store("Note 2")
    assert mem.count() == 2

    assert mem.delete(id1) is True
    assert mem.count() == 1
    assert mem.delete("nonexistent_id") is False

    mem.clear()
    assert mem.count() == 0
