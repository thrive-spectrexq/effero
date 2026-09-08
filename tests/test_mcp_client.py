"""Tests for external MCPClient tool mounting and JSON-RPC communication."""

import sys

import pytest

from effero.protocols.mcp_client import MCPClient
from effero.sdk.skill import SafetyClass, SkillRegistry


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
