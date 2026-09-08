"""MCP server — exposes Effero skills to external MCP clients.

Implements the Model Context Protocol (MCP) over stdio transport,
allowing Claude, IDE agents, and other MCP clients to call Effero skills.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from effero import __version__

if TYPE_CHECKING:
    from effero.sdk.skill import SkillRegistry, SkillSpec

logger = logging.getLogger(__name__)


class MCPServer:
    """Serves Effero skills over the MCP protocol."""

    def __init__(self, skills: SkillRegistry) -> None:
        self.skills = skills

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle an incoming MCP JSON-RPC request."""
        method = request.get("method", "")
        req_id = request.get("id")
        result: dict[str, Any]

        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "effero", "version": __version__},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            tools = []
            for s in self.skills.list():
                # Note: list() returns string names, we need the specs
                spec = self.skills.get(s)
                tools.append(
                    {
                        "name": spec.name,
                        "description": spec.description or "",
                        "inputSchema": self._build_input_schema(spec),
                    }
                )
            result = {"tools": tools}
        elif method == "tools/call":
            result = await self._call_tool(request.get("params", {}))
        elif method == "notifications/initialized":
            return {}  # notification, no response needed
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            }

        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    async def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", ""))
        arguments = params.get("arguments", {})
        try:
            s = self.skills.get(name)
        except KeyError:
            return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}

        try:
            result = s(**arguments)
            if hasattr(result, "__await__"):
                result = await result
            return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}

    @staticmethod
    def _build_input_schema(skill_spec: SkillSpec) -> dict[str, Any]:
        """Build JSON Schema for a skill's input parameters."""
        import inspect

        sig = skill_spec.signature
        properties = {}
        required = []
        for pname, param in sig.parameters.items():
            prop: dict[str, Any] = {"type": "string"}  # default
            if param.annotation != inspect.Parameter.empty:
                ann = param.annotation
                if ann is str or ann == "str":
                    prop = {"type": "string"}
                elif ann is int or ann == "int":
                    prop = {"type": "integer"}
                elif ann is float or ann == "float":
                    prop = {"type": "number"}
                elif ann is bool or ann == "bool":
                    prop = {"type": "boolean"}
            properties[pname] = prop
            if param.default is inspect.Parameter.empty:
                required.append(pname)
        return {"type": "object", "properties": properties, "required": required}
