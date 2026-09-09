"""Unit tests for AnthropicBackend."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from effero.core.router.anthropic_backend import AnthropicBackend
from effero.core.router.base import LLMRequest


@pytest.mark.asyncio
async def test_anthropic_complete_text_and_tool_use(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify AnthropicBackend formats request and parses text + tool_use blocks."""
    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    text_block = SimpleNamespace(type="text", text="I will turn on the light.")
    tool_block = SimpleNamespace(type="tool_use", id="tu_123", name="iot.lights.toggle", input={"device_id": "lamp_1"})
    usage = SimpleNamespace(input_tokens=15, output_tokens=30)
    fake_response = SimpleNamespace(
        content=[text_block, tool_block],
        usage=usage,
        model="claude-sonnet-4-20250514",
    )

    mock_client.messages.create = AsyncMock(return_value=fake_response)
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)

    backend = AnthropicBackend(model="claude-sonnet-4-20250514", api_key="test-api-key")
    request = LLMRequest(
        messages=[{"role": "user", "content": "Toggle the lamp"}],
        system="You are home assistant",
        tools=[{"name": "iot.lights.toggle", "description": "Toggle light"}],
    )

    resp = await backend.complete(request)
    assert resp.content == "I will turn on the light."
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "iot.lights.toggle"
    assert resp.tool_calls[0].arguments == {"device_id": "lamp_1"}
    assert resp.usage == {"input_tokens": 15, "output_tokens": 30}
    assert resp.backend == "anthropic"


@pytest.mark.asyncio
async def test_anthropic_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify error raised when api_key is missing."""
    mock_anthropic = MagicMock()
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    backend = AnthropicBackend(api_key=None)
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    with pytest.raises(RuntimeError, match="Anthropic API key is not set"):
        await backend.complete(request)


@pytest.mark.asyncio
async def test_anthropic_api_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify runtime errors from Anthropic API are caught and wrapped."""
    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=ConnectionError("Network down"))
    mock_anthropic.AsyncAnthropic.return_value = mock_client
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)

    backend = AnthropicBackend(api_key="test-key")
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    with pytest.raises(RuntimeError, match="Anthropic API error"):
        await backend.complete(request)


@pytest.mark.asyncio
async def test_anthropic_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify is_available checks package presence and api_key."""
    mock_anthropic = MagicMock()
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)

    b1 = AnthropicBackend(api_key="key")
    assert await b1.is_available() is True

    b2 = AnthropicBackend(api_key=None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    b2.api_key = None
    assert await b2.is_available() is False
