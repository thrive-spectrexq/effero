"""Tests for LiteRT-LM backend and router integration using concrete contract test doubles."""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from typing import Any

import pytest

from effero.config import ModelConfig
from effero.core.router.base import LLMRequest
from effero.core.router.litert_backend import LiteRTLMBackend
from effero.core.router.router import ModelRouter


class FakeConversation:
    """Explicit test double for LiteRT-LM conversation session."""

    def __init__(self, response_chunks: list[dict[str, list[dict[str, str]]]]) -> None:
        self.response_chunks = response_chunks
        self.system_instruction: str | None = None
        self.received_prompts: list[str] = []

    def __enter__(self) -> FakeConversation:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    def set_system_instruction(self, instruction: str) -> None:
        self.system_instruction = instruction

    def send_message_async(self, prompt: str) -> Iterator[dict[str, list[dict[str, str]]]]:
        self.received_prompts.append(prompt)
        yield from self.response_chunks


class FakeBackendEnum:
    """Backend hardware acceleration targets."""

    @staticmethod
    def GPU() -> str:
        return "GPU_BACKEND"

    @staticmethod
    def NPU() -> str:
        return "NPU_BACKEND"

    @staticmethod
    def CPU() -> str:
        return "CPU_BACKEND"


class FakeLiteRTEngine:
    """Explicit structural test double for litert_lm.Engine."""

    def __init__(self, model: str, **kwargs: Any) -> None:
        self.model = model
        self.kwargs = kwargs
        self.closed = False
        self.last_confidence = 0.92
        self.active_conversation: FakeConversation | None = None

    def create_conversation(self) -> FakeConversation:
        if self.active_conversation is not None:
            return self.active_conversation
        return FakeConversation([])

    def get_last_confidence(self) -> float:
        return self.last_confidence

    def close(self) -> None:
        self.closed = True


class FakeLiteRTModule:
    """Emulates litert_lm module surface."""

    Backend = FakeBackendEnum
    Engine = FakeLiteRTEngine


def test_litert_router_factory() -> None:
    """Verify ModelRouter creates LiteRTLMBackend for litert and litert-lm providers."""
    for provider in ("litert", "litert-lm", "litertlm"):
        config = ModelConfig(backend=provider, model="/path/to/gemma-3-1b.litertlm", device="npu")
        router = ModelRouter(config)
        assert len(router.backends) == 1
        backend = router.backends[0]
        assert isinstance(backend, LiteRTLMBackend)
        assert backend.model == "/path/to/gemma-3-1b.litertlm"
        assert backend.device == "npu"


@pytest.mark.asyncio
async def test_litert_is_available_without_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_available() should return False when litert_lm is not installed."""
    backend = LiteRTLMBackend(model="gemma-3-1b.litertlm")
    # Ensure litert_lm is not in sys.modules
    monkeypatch.setitem(sys.modules, "litert_lm", None)  # type: ignore[assignment]
    assert await backend.is_available() is False


@pytest.mark.asyncio
async def test_litert_is_available_with_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_available() should return True when litert_lm is importable and model is set."""
    backend = LiteRTLMBackend(model="gemma-3-1b")
    fake_mod = types.ModuleType("litert_lm")
    monkeypatch.setitem(sys.modules, "litert_lm", fake_mod)
    assert await backend.is_available() is True


def test_device_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify device string resolves to corresponding litert_lm.Backend target."""
    fake_litert = FakeLiteRTModule

    gpu_backend = LiteRTLMBackend(model="model.litertlm", device="gpu")
    assert gpu_backend._resolve_backend_type(fake_litert) == "GPU_BACKEND"

    npu_backend = LiteRTLMBackend(model="model.litertlm", device="npu")
    assert npu_backend._resolve_backend_type(fake_litert) == "NPU_BACKEND"

    cpu_backend = LiteRTLMBackend(model="model.litertlm", device="cpu")
    assert cpu_backend._resolve_backend_type(fake_litert) == "CPU_BACKEND"


@pytest.mark.asyncio
async def test_litert_complete_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify complete() runs conversation on LiteRT-LM engine and formats response."""
    fake_mod = types.ModuleType("litert_lm")
    fake_mod.Backend = FakeBackendEnum  # type: ignore[attr-defined]

    conv = FakeConversation(
        [
            {"content": [{"text": "Navigation "}]},
            {"content": [{"text": "trajectory planned."}]},
        ]
    )
    engine = FakeLiteRTEngine(model="gemma-3-1b.litertlm")
    engine.active_conversation = conv

    def engine_factory(model: str, **kwargs: Any) -> FakeLiteRTEngine:
        return engine

    fake_mod.Engine = engine_factory  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "litert_lm", fake_mod)

    backend = LiteRTLMBackend(model="gemma-3-1b.litertlm", device="npu")
    request = LLMRequest(
        messages=[{"role": "user", "content": "plan navigation to waypoint"}],
        system="You are a robotics navigation planner.",
    )

    response = await backend.complete(request)

    assert response.content == "Navigation trajectory planned."
    assert response.backend == "litert"
    assert response.model == "gemma-3-1b.litertlm"
    assert response.confidence == 0.92
    assert response.tool_calls == []


@pytest.mark.asyncio
async def test_litert_tool_calling_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify tool call in json code fence is correctly extracted from model output."""
    fake_mod = types.ModuleType("litert_lm")
    fake_mod.Backend = FakeBackendEnum  # type: ignore[attr-defined]

    tool_json_text = (
        "I will set the lights now.\n"
        "```json\n"
        '{"tool_call": {"name": "iot.lights.turn_on", "arguments": {"room": "kitchen"}}}\n'
        "```"
    )
    conv = FakeConversation([{"content": [{"text": tool_json_text}]}])
    engine = FakeLiteRTEngine(model="gemma-3-1b.litertlm")
    engine.active_conversation = conv

    fake_mod.Engine = lambda model, **kwargs: engine  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "litert_lm", fake_mod)

    backend = LiteRTLMBackend(model="gemma-3-1b.litertlm")
    request = LLMRequest(
        messages=[{"role": "user", "content": "turn on kitchen lights"}],
        tools=[{"name": "iot.lights.turn_on", "description": "Turn on light in room"}],
    )

    response = await backend.complete(request)

    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert call.name == "iot.lights.turn_on"
    assert call.arguments == {"room": "kitchen"}


def test_litert_close() -> None:
    """Verify close() releases the engine."""
    backend = LiteRTLMBackend(model="test.litertlm")
    fake_engine = FakeLiteRTEngine("test.litertlm")
    backend._engine = fake_engine

    backend.close()
    assert fake_engine.closed is True
    assert backend._engine is None
