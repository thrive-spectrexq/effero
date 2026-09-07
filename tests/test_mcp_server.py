"""Tests for MCPServer."""

from __future__ import annotations

import inspect

import pytest

from effero.protocols.mcp_server import MCPServer
from effero.sdk.skill import SafetyClass, SkillRegistry, SkillSpec


@pytest.fixture
def mcp_server():
    """Create an MCP server with a test skill."""
    reg = SkillRegistry()

    def echo_fn(message: str) -> dict:
        return {"echo": message}

    spec = SkillSpec(
        name="test.echo",
        description="Echo back a message",
        safety_class=SafetyClass.READ_ONLY,
        func=echo_fn,
        signature=inspect.signature(echo_fn),
    )
    reg.register(spec)
    return MCPServer(reg)


@pytest.mark.asyncio
async def test_initialize(mcp_server) -> None:
    response = await mcp_server.handle_request({"method": "initialize", "id": 1})
    assert response["result"]["protocolVersion"] == "2024-11-05"
    assert response["result"]["serverInfo"]["name"] == "effero"


@pytest.mark.asyncio
async def test_tools_list(mcp_server) -> None:
    response = await mcp_server.handle_request({"method": "tools/list", "id": 2})
    tools = response["result"]["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "test.echo"


@pytest.mark.asyncio
async def test_tools_call(mcp_server) -> None:
    response = await mcp_server.handle_request(
        {
            "method": "tools/call",
            "id": 3,
            "params": {"name": "test.echo", "arguments": {"message": "hello"}},
        }
    )
    content = response["result"]["content"]
    assert len(content) == 1
    assert "hello" in content[0]["text"]


@pytest.mark.asyncio
async def test_unknown_method(mcp_server) -> None:
    response = await mcp_server.handle_request({"method": "unknown/method", "id": 4})
    assert "error" in response
