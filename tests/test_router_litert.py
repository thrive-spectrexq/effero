"""Tests for LiteRT-LM backend and router integration."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from effero.config import ModelConfig
from effero.core.router.base import LLMRequest
from effero.core.router.litert_backend import LiteRTLMBackend
from effero.core.router.router import ModelRouter


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
async def test_litert_is_available_with_mock_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_available() should return True when litert_lm is importable and model is set."""
    backend = LiteRTLMBackend(model="gemma-3-1b")
    mock_module = MagicMock()
    monkeypatch.setitem(sys.modules, "litert_lm", mock_module)
    assert await backend.is_available() is True


def test_device_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify device string resolves to corresponding litert_lm.Backend target."""
    mock_litert = MagicMock()
    mock_litert.Backend.GPU.return_value = "GPU_BACKEND"
    mock_litert.Backend.NPU.return_value = "NPU_BACKEND"
    mock_litert.Backend.CPU.return_value = "CPU_BACKEND"

    gpu_backend = LiteRTLMBackend(model="model.litertlm", device="gpu")
    assert gpu_backend._resolve_backend_type(mock_litert) == "GPU_BACKEND"

    npu_backend = LiteRTLMBackend(model="model.litertlm", device="npu")
    assert npu_backend._resolve_backend_type(mock_litert) == "NPU_BACKEND"

    cpu_backend = LiteRTLMBackend(model="model.litertlm", device="cpu")
    assert cpu_backend._resolve_backend_type(mock_litert) == "CPU_BACKEND"


@pytest.mark.asyncio
async def test_litert_complete_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify complete() runs conversation on mocked LiteRT-LM engine and formats response."""
    mock_litert = MagicMock()
    mock_conversation = MagicMock()
    # Mock send_message_async returning streaming content chunks
    mock_conversation.send_message_async.return_value = [
        {"content": [{"text": "Navigation "}]},
        {"content": [{"text": "trajectory planned."}]},
    ]
    # Context manager protocol for conversation
    mock_conversation.__enter__.return_value = mock_conversation
    mock_conversation.__exit__.return_value = None

    mock_engine = MagicMock()
    mock_engine.create_conversation.return_value = mock_conversation
    mock_engine.get_last_confidence.return_value = 0.92
    mock_litert.Engine.return_value = mock_engine

    monkeypatch.setitem(sys.modules, "litert_lm", mock_litert)

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
    mock_litert = MagicMock()
    mock_conversation = MagicMock()
    tool_json_text = (
        "I will set the lights now.\n"
        "```json\n"
        '{"tool_call": {"name": "iot.lights.turn_on", "arguments": {"room": "kitchen"}}}\n'
        "```"
    )
    mock_conversation.send_message_async.return_value = [{"content": [{"text": tool_json_text}]}]
    mock_conversation.__enter__.return_value = mock_conversation
    mock_conversation.__exit__.return_value = None

    mock_engine = MagicMock()
    mock_engine.create_conversation.return_value = mock_conversation
    mock_litert.Engine.return_value = mock_engine
    monkeypatch.setitem(sys.modules, "litert_lm", mock_litert)

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
    mock_engine = MagicMock()
    backend._engine = mock_engine

    backend.close()
    mock_engine.close.assert_called_once()
    assert backend._engine is None
