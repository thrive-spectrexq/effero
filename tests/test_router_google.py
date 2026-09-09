"""Unit tests for GoogleBackend."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from effero.core.router.base import LLMRequest
from effero.core.router.google_backend import GoogleBackend


@pytest.mark.asyncio
async def test_google_complete_text_and_function_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify GoogleBackend converts messages and parses text and function call parts."""
    mock_genai = MagicMock()
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client

    # Create response parts
    text_part = SimpleNamespace(text="Adjusting thermostat", function_call=None)
    fc_part = SimpleNamespace(
        text=None,
        function_call=SimpleNamespace(name="iot.thermostat.set_temperature", args={"celsius": 21.5}),
    )
    candidate = SimpleNamespace(content=SimpleNamespace(parts=[text_part, fc_part]))
    usage = SimpleNamespace(prompt_token_count=10, candidates_token_count=20, total_token_count=30)
    fake_response = SimpleNamespace(candidates=[candidate], usage_metadata=usage)

    mock_client.aio.models.generate_content = AsyncMock(return_value=fake_response)
    monkeypatch.setitem(sys.modules, "google.genai", mock_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", MagicMock())

    backend = GoogleBackend(model="gemini-2.5-flash", api_key="test-api-key")
    request = LLMRequest(
        messages=[{"role": "user", "content": "Set temp to 21.5"}],
        system="Home system",
        tools=[
            {
                "name": "iot.thermostat.set_temperature",
                "description": "Set temp",
                "parameters": {"type": "object", "properties": {"celsius": {"type": "number"}}},
            }
        ],
    )

    resp = await backend.complete(request)
    assert resp.content == "Adjusting thermostat"
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "iot.thermostat.set_temperature"
    assert resp.tool_calls[0].arguments == {"celsius": 21.5}
    assert resp.usage == {"prompt_token_count": 10, "candidates_token_count": 20, "total_token_count": 30}
    assert resp.backend == "google"


@pytest.mark.asyncio
async def test_google_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify error raised when api_key is missing."""
    mock_genai = MagicMock()
    monkeypatch.setitem(sys.modules, "google.genai", mock_genai)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    backend = GoogleBackend(api_key=None)
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    with pytest.raises(RuntimeError, match="Gemini API key is not set"):
        await backend.complete(request)


@pytest.mark.asyncio
async def test_google_api_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify runtime errors from Google Gemini API are caught and wrapped."""
    mock_genai = MagicMock()
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=Exception("API limit"))
    mock_genai.Client.return_value = mock_client
    monkeypatch.setitem(sys.modules, "google.genai", mock_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", MagicMock())

    backend = GoogleBackend(api_key="test-key")
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    with pytest.raises(RuntimeError, match="Google Gemini API error"):
        await backend.complete(request)


@pytest.mark.asyncio
async def test_google_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify is_available checks package presence and api_key."""
    mock_genai = MagicMock()
    monkeypatch.setitem(sys.modules, "google.genai", mock_genai)

    b1 = GoogleBackend(api_key="key")
    assert await b1.is_available() is True

    b2 = GoogleBackend(api_key=None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    b2.api_key = None
    assert await b2.is_available() is False
