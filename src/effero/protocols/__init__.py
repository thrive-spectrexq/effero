"""Protocol adapters: MCP (skill/tool exposure), A2A (agent-to-agent
coordination), and Wyoming (streaming voice transport).
"""
from __future__ import annotations

from effero.protocols.a2a import A2AClient, AgentCard
from effero.protocols.mcp_server import MCPServer

__all__ = ["MCPServer", "A2AClient", "AgentCard"]
