"""Unit tests for OpenAIBackend."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from effero.core.router.base import LLMRequest
from effero.core.router.openai_backend import OpenAIBackend


@pytest.mark.asyncio
async def test_openai_complete_text_and_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify OpenAIBackend handles completion, tool calls with JSON parsing and raw fallback."""
    mock_openai = MagicMock()
    mock_client = MagicMock()
    mock_openai.AsyncOpenAI.return_value = mock_client

    tc1 = SimpleNamespace(
        id="tc1",
        type="function",
        function=SimpleNamespace(name="iot.lights.toggle", arguments='{"room": "kitchen"}'),
    )
    tc2 = SimpleNamespace(
        id="tc2",
        type="function",
        function=SimpleNamespace(name="custom.raw", arguments="invalid-json-text"),
    )

    choice = SimpleNamespace(
        message=SimpleNamespace(content="Done", tool_calls=[tc1, tc2]),
        confidence=0.89,
    )
    usage = SimpleNamespace(prompt_tokens=12, completion_tokens=24, total_tokens=36)
    fake_response = SimpleNamespace(choices=[choice], usage=usage, model="gpt-4o")

    mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
    monkeypatch.setitem(sys.modules, "openai", mock_openai)

    backend = OpenAIBackend(model="gpt-4o", api_key="sk-test")
    request = LLMRequest(
        messages=[{"role": "user", "content": "Toggle kitchen light"}],
        system="Home agent",
        tools=[{"name": "iot.lights.toggle", "description": "Toggle light"}],
    )

    resp = await backend.complete(request)
    assert resp.content == "Done"
    assert len(resp.tool_calls) == 2
    assert resp.tool_calls[0].name == "iot.lights.toggle"
    assert resp.tool_calls[0].arguments == {"room": "kitchen"}
    assert resp.tool_calls[1].name == "custom.raw"
    assert resp.tool_calls[1].arguments == {"_raw_args": "invalid-json-text"}
    assert resp.confidence == 0.89
    assert resp.usage == {"prompt_tokens": 12, "completion_tokens": 24, "total_tokens": 36}


@pytest.mark.asyncio
async def test_openai_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify error raised when OpenAI API key is not set."""
    mock_openai = MagicMock()
    monkeypatch.setitem(sys.modules, "openai", mock_openai)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    backend = OpenAIBackend(model="gpt-4o", api_key=None)
    request = LLMRequest(messages=[{"role": "user", "content": "hello"}])
    with pytest.raises(RuntimeError, match="OpenAI API key is not set"):
        await backend.complete(request)


@pytest.mark.asyncio
async def test_openai_api_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify OpenAI API errors are caught and wrapped."""
    mock_openai = MagicMock()
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("Rate limit"))
    mock_openai.AsyncOpenAI.return_value = mock_client
    monkeypatch.setitem(sys.modules, "openai", mock_openai)

    backend = OpenAIBackend(model="gpt-4o", api_key="sk-test")
    request = LLMRequest(messages=[{"role": "user", "content": "hello"}])
    with pytest.raises(RuntimeError, match="OpenAI API error"):
        await backend.complete(request)


@pytest.mark.asyncio
async def test_openai_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify is_available checks package presence and api_key."""
    mock_openai = MagicMock()
    monkeypatch.setitem(sys.modules, "openai", mock_openai)

    b1 = OpenAIBackend(model="gpt-4o", api_key="sk-test")
    assert await b1.is_available() is True

    b2 = OpenAIBackend(model="gpt-4o", api_key=None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    b2.api_key = None
    assert await b2.is_available() is False
