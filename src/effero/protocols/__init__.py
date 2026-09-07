"""Protocol adapters: MCP (skill/tool exposure), A2A (agent-to-agent
coordination), and Wyoming (streaming voice transport).
"""

from __future__ import annotations

from effero.protocols.a2a import (
    A2AClient,
    A2ATaskManager,
    AgentCard,
    TaskMessage,
    TaskState,
)
from effero.protocols.mcp_server import MCPServer
from effero.protocols.wyoming import WyomingClient, WyomingEvent, WyomingServer

__all__ = [
    "MCPServer",
    "A2AClient",
    "AgentCard",
    "TaskMessage",
    "TaskState",
    "A2ATaskManager",
    "WyomingServer",
    "WyomingClient",
    "WyomingEvent",
]
