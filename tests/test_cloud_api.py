"""Tests for CloudAPIAdapter REST client implementation."""

from __future__ import annotations

import httpx
import pytest
import respx

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
@respx.mock
async def test_cloud_api_execute_json_and_text():
    respx.post("https://api.example.com/items").respond(200, json={"item_id": 42, "status": "created"})
    respx.get("https://api.example.com/raw").respond(200, text="raw-response-text")
    respx.get("https://api.example.com/").respond(200, json={"healthy": True, "version": "1.0"})

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
@respx.mock
async def test_cloud_api_error_handling():
    respx.get("https://api.example.com/fail").respond(500, text="Internal Server Error")
    respx.get("https://api.example.com/").respond(503, text="Service Unavailable")

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
