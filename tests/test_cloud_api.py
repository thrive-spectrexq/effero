"""Tests for CloudAPIAdapter REST client implementation."""

from __future__ import annotations

import httpx
import pytest

from effero.adapters.cloud_api.client import CloudAPIAdapter


@pytest.mark.asyncio
async def test_cloud_api_lifecycle():
    adapter = CloudAPIAdapter(base_url="https://api.example.com", auth_token="secret_token")
    assert adapter.headers["Authorization"] == "Bearer secret_token"

    # Not connected error
    with pytest.raises(RuntimeError, match="CloudAPIAdapter not connected"):
        await adapter.execute("test", {"endpoint": "/status"})

    await adapter.connect()
    assert adapter._client is not None

    await adapter.disconnect()
    assert adapter._client is None


@pytest.mark.asyncio
async def test_cloud_api_no_httpx(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("effero.adapters.cloud_api.client.HAS_HTTPX", False)
    adapter = CloudAPIAdapter(base_url="https://api.example.com")
    with pytest.raises(RuntimeError, match="httpx is required"):
        await adapter.connect()


@pytest.mark.asyncio
async def test_cloud_api_execute_json_and_text(monkeypatch: pytest.MonkeyPatch):
    def handle_request(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/items" and request.method == "POST":
            return httpx.Response(200, json={"item_id": 42, "status": "created"})
        if request.url.path == "/raw" and request.method == "GET":
            return httpx.Response(200, text="raw-response-text")
        if request.url.path == "/" and request.method == "GET":
            return httpx.Response(200, json={"healthy": True, "version": "1.0"})
        return httpx.Response(404)

    mock_transport = httpx.MockTransport(handle_request)
    orig_client = httpx.AsyncClient
    monkeypatch.setattr(
        "effero.adapters.cloud_api.client.httpx.AsyncClient",
        lambda *args, **kwargs: orig_client(*args, transport=mock_transport, **kwargs),
    )

    adapter = CloudAPIAdapter(base_url="https://api.example.com")
    await adapter.connect()

    try:
        # JSON response
        result = await adapter.execute("create", {"method": "POST", "endpoint": "/items", "payload": {"name": "gear"}})
        assert result["item_id"] == 42
        assert result["status"] == "created"

        # Non-JSON text response fallback
        text_result = await adapter.execute("get_raw", {"method": "GET", "endpoint": "/raw"})
        assert text_result == {"text": "raw-response-text"}

        # read_state
        state = await adapter.read_state()
        assert state == {"healthy": True, "version": "1.0"}
    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
async def test_cloud_api_error_handling(monkeypatch: pytest.MonkeyPatch):
    def handle_request(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fail":
            return httpx.Response(500, text="Internal Server Error")
        if request.url.path == "/":
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(404)

    mock_transport = httpx.MockTransport(handle_request)
    orig_client = httpx.AsyncClient
    monkeypatch.setattr(
        "effero.adapters.cloud_api.client.httpx.AsyncClient",
        lambda *args, **kwargs: orig_client(*args, transport=mock_transport, **kwargs),
    )

    adapter = CloudAPIAdapter(base_url="https://api.example.com")
    await adapter.connect()

    try:
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.execute("failing", {"method": "GET", "endpoint": "/fail"})

        # read_state failure returns previous state gracefully
        state = await adapter.read_state()
        assert state == {}
    finally:
        await adapter.disconnect()
