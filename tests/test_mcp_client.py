"""Tests for external MCPClient tool mounting and JSON-RPC communication."""

import sys

import pytest

from effero.protocols.mcp_client import MCPClient
from effero.sdk.skill import SafetyClass, SkillRegistry, SkillSpec


@pytest.mark.asyncio
async def test_mcp_client_stdio_handshake_and_call():
    """Test connecting to a python-based dummy MCP server via stdio."""
    # Spawn a tiny Python child process that implements basic JSON-RPC 2.0 MCP
    server_script = """import sys, json

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        method = req.get("method")
        req_id = req.get("id")

        if method == "initialize":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "test"}, "capabilities": {}}}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "calc_add",
                            "description": "Add two numbers",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                                "required": ["a", "b"]
                            }
                        }
                    ]
                }
            }
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
        elif method == "tools/call":
            params = req.get("params", {})
            args = params.get("arguments", {})
            total = args.get("a", 0) + args.get("b", 0)
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": f"Result: {total}"}]}
            }
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
    except Exception as e:
        sys.stderr.write(f"Server error: {e}\\n")
        sys.stderr.flush()
"""

    client = MCPClient(
        name="test_calc",
        command=sys.executable,
        args=["-u", "-c", server_script],
        default_safety_class=SafetyClass.READ_ONLY,
    )

    try:
        await client.connect()
        tools = await client.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "calc_add"

        # Mount into a fresh registry
        registry = SkillRegistry()
        mounted = client.mount_tools(registry, prefix="ext")
        assert mounted == ["ext.calc_add"]

        spec = registry.get("ext.calc_add")
        assert spec.safety_class == SafetyClass.READ_ONLY
        assert "Add two numbers" in spec.description

        # Call tool through spec
        result = await spec(a=15, b=27)
        assert result == "Result: 42"

    finally:
        await client.close()


@pytest.mark.asyncio
async def test_mcp_client_http_jsonrpc_handshake_and_call():
    """Test connecting to an external MCP server via real HTTP JSON-RPC endpoint."""
    import httpx
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from effero.protocols.mcp_server import MCPServer

    reg = SkillRegistry()

    def multiply(x: float, y: float) -> dict:
        return {"result": x * y}

    import inspect

    spec = SkillSpec(
        name="math_multiply",
        description="Multiply two numbers",
        safety_class=SafetyClass.READ_ONLY,
        func=multiply,
        signature=inspect.signature(multiply),
    )
    reg.register(spec)
    server = MCPServer(reg)

    async def mcp_endpoint(request: Request) -> JSONResponse:
        data = await request.json()
        resp = await server.handle_request(data)
        return JSONResponse(resp)

    app = Starlette(routes=[Route("/mcp", mcp_endpoint, methods=["POST"])])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        client = MCPClient(
            name="test_remote_http",
            url="http://test/mcp",
            default_safety_class=SafetyClass.READ_ONLY,
            http_client=http_client,
        )
        try:
            await client.connect()
            tools = await client.list_tools()
            assert len(tools) == 1
            assert tools[0]["name"] == "math_multiply"

            fresh_registry = SkillRegistry()
            mounted = client.mount_tools(fresh_registry, prefix="remote")
            assert mounted == ["remote.math_multiply"]

            tool_spec = fresh_registry.get("remote.math_multiply")
            res = await tool_spec(x=6.0, y=7.0)
            assert "42" in res

            # Tool failure propagation when isError is True
            with pytest.raises(RuntimeError, match="MCP tool 'math_multiply' error"):
                await client.call_tool("math_multiply", {"x": "invalid_number", "y": 7.0})

            # Unknown tool failure
            with pytest.raises(RuntimeError, match="Unknown tool"):
                await client.call_tool("nonexistent_tool", {})
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_mcp_client_http_server_error_and_unconnected():
    """Test HTTP 500 JSON-RPC error extraction and unconnected state exception."""
    import httpx
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def failing_endpoint(request: Request) -> JSONResponse:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "Internal gateway failure"}},
            status_code=500,
        )

    app = Starlette(routes=[Route("/mcp", failing_endpoint, methods=["POST"])])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        client = MCPClient(name="test_err", url="http://test/mcp", http_client=http_client)

        # Calling send_request before connect should raise ConnectionError if http_client is None
        unconnected_client = MCPClient(name="unconnected", url="http://test/mcp")
        with pytest.raises(ConnectionError, match="Call connect\\(\\) first"):
            await unconnected_client._send_request("test", {})

        # Connecting to failing endpoint extracts JSON-RPC error even with HTTP 500
        with pytest.raises(RuntimeError, match="MCP error -32000: Internal gateway failure"):
            await client.connect()
