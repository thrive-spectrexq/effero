"""MCP Client — connects to external MCP servers and mounts their tools as Effero skills."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from collections.abc import Callable
from typing import Any

import httpx

from effero import __version__
from effero.sdk.skill import SafetyClass, SkillRegistry, SkillSpec

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for external Model Context Protocol (MCP) servers.

    Supports stdio sub-processes and HTTP/SSE JSON-RPC 2.0 endpoints.
    Discovered tools are automatically transformed and mounted into an Effero SkillRegistry.
    """

    def __init__(
        self,
        name: str,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        default_safety_class: SafetyClass | str = SafetyClass.ACT_WITH_APPROVAL,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.url = url
        if isinstance(default_safety_class, str):
            self.default_safety_class = SafetyClass(default_safety_class.lower())
        else:
            self.default_safety_class = default_safety_class

        self._process: asyncio.subprocess.Process | None = None
        self._http_client: httpx.AsyncClient | None = http_client
        self._request_id = 0
        self._pending_requests: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._tools: list[dict[str, Any]] = []
        self._connected = False

    async def connect(self) -> None:
        """Connect to the external MCP server via stdio process."""
        if self._connected:
            return

        if self.command:
            full_env = dict(os.environ)
            full_env.update(self.env)
            cmd_args = [self.command, *self.args]

            logger.info(f"Starting external MCP server '{self.name}': {' '.join(cmd_args)}")
            self._process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=full_env,
            )
            self._reader_task = asyncio.create_task(self._read_loop())
            self._connected = True

            # Send initialize handshake
            init_resp = await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "effero-client", "version": __version__},
                },
            )
            logger.debug(f"MCP server '{self.name}' initialized: {init_resp}")

            # Send initialized notification
            await self._send_notification("notifications/initialized", {})

        elif self.url:
            if self._http_client is None:
                self._http_client = httpx.AsyncClient(timeout=30.0)
            self._connected = True

            # Send initialize handshake over HTTP
            init_resp = await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "effero-client", "version": __version__},
                },
            )
            logger.debug(f"MCP HTTP server '{self.name}' initialized: {init_resp}")

            # Send initialized notification
            await self._send_notification("notifications/initialized", {})
            logger.info(f"Connected to external MCP endpoint '{self.name}' at {self.url}")
        else:
            raise ValueError(f"MCPClient '{self.name}' requires either 'command' or 'url'")

    async def list_tools(self) -> list[dict[str, Any]]:
        """Query the MCP server for available tools ('tools/list')."""
        if not self._connected:
            await self.connect()

        response = await self._send_request("tools/list", {})
        self._tools = response.get("tools", [])
        logger.info(f"Discovered {len(self._tools)} tools from MCP server '{self.name}'")
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Invoke a tool on the external MCP server ('tools/call')."""
        if not self._connected:
            await self.connect()

        params = {"name": name, "arguments": arguments or {}}
        response = await self._send_request("tools/call", params)
        content = response.get("content", [])
        if response.get("isError"):
            err_msg = ""
            if isinstance(content, list) and content and isinstance(content[0], dict):
                err_msg = content[0].get("text", "")
            else:
                err_msg = str(content)
            raise RuntimeError(f"MCP tool '{name}' error: {err_msg}")
        if isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict):
            if content[0].get("type") == "text":
                return content[0].get("text", "")
        return content

    def mount_tools(
        self,
        registry: SkillRegistry,
        prefix: str | None = None,
        safety_class_overrides: dict[str, SafetyClass] | None = None,
    ) -> list[str]:
        """Mount all discovered tools into an Effero SkillRegistry."""
        mounted_names: list[str] = []
        prefix_str = f"{prefix or self.name}."
        overrides = safety_class_overrides or {}

        for tool in self._tools:
            raw_name = tool["name"]
            qualified_name = f"{prefix_str}{raw_name}" if not raw_name.startswith(prefix_str) else raw_name
            description = tool.get("description") or f"External MCP tool {raw_name}"
            safety = overrides.get(raw_name, overrides.get(qualified_name, self.default_safety_class))

            def _make_tool_func(tool_name: str) -> Callable[..., Any]:
                async def _tool_caller(**kwargs: Any) -> Any:
                    return await self.call_tool(tool_name, kwargs)

                return _tool_caller

            tool_callable = _make_tool_func(raw_name)

            # Build genuine inspect signature from inputSchema
            properties = tool.get("inputSchema", {}).get("properties", {})
            required_props = set(tool.get("inputSchema", {}).get("required", []))
            type_mapping: dict[str, type] = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "object": dict,
                "array": list,
            }
            params = []
            for p_name, p_info in properties.items():
                p_type = type_mapping.get(p_info.get("type", ""), Any) if isinstance(p_info, dict) else Any
                p_default = inspect.Parameter.empty if p_name in required_props else None
                params.append(
                    inspect.Parameter(
                        name=p_name,
                        kind=inspect.Parameter.KEYWORD_ONLY,
                        annotation=p_type,
                        default=p_default,
                    )
                )
            sig = inspect.Signature(parameters=params)

            spec = SkillSpec(
                name=qualified_name,
                description=description,
                safety_class=safety,
                func=tool_callable,
                signature=sig,
            )

            try:
                registry.register(spec)
                mounted_names.append(qualified_name)
            except ValueError:
                logger.warning(f"Skill '{qualified_name}' is already registered; skipping.")

        return mounted_names

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC 2.0 request and await the response."""
        self._request_id += 1
        req_id = self._request_id
        req: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        # HTTP / SSE transport branch
        if self.url:
            if not self._http_client:
                raise ConnectionError(f"MCP HTTP client '{self.name}' not connected. Call connect() first.")
            resp = await self._http_client.post(
                self.url,
                json=req,
                headers={"Content-Type": "application/json"},
            )
            try:
                data = resp.json()
            except Exception:
                resp.raise_for_status()
                raise
            if isinstance(data, dict) and "error" in data:
                err = data["error"]
                err_code = err.get("code") if isinstance(err, dict) else -32000
                err_msg = err.get("message") if isinstance(err, dict) else str(err)
                raise RuntimeError(f"MCP error {err_code}: {err_msg}")
            resp.raise_for_status()
            return data.get("result", {})

        # Subprocess stdio transport branch
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending_requests[req_id] = future

        if self._process and self._process.stdin:
            line = (json.dumps(req) + "\n").encode("utf-8")
            self._process.stdin.write(line)
            await self._process.stdin.drain()
        else:
            raise ConnectionError(f"MCP server '{self.name}' transport stream not available")

        # Wait for response with timeout
        try:
            return await asyncio.wait_for(future, timeout=15.0)
        except TimeoutError as e:
            self._pending_requests.pop(req_id, None)
            raise TimeoutError(f"Timeout waiting for MCP response to method '{method}' (id={req_id})") from e

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC 2.0 notification."""
        notif = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        if self.url:
            if self._http_client:
                try:
                    await self._http_client.post(
                        self.url,
                        json=notif,
                        headers={"Content-Type": "application/json"},
                    )
                except Exception as e:
                    logger.warning(f"Failed to send MCP notification to '{self.name}': {e}")
            return

        if self._process and self._process.stdin:
            line = (json.dumps(notif) + "\n").encode("utf-8")
            self._process.stdin.write(line)
            await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        """Continually read JSON-RPC lines from child process stdout."""
        if not self._process or not self._process.stdout:
            return

        while True:
            line = await self._process.stdout.readline()
            if not line:
                break

            try:
                data = json.loads(line.decode("utf-8").strip())
                req_id = data.get("id")
                if req_id in self._pending_requests:
                    future = self._pending_requests.pop(req_id)
                    if not future.done():
                        if "error" in data:
                            err = data["error"]
                            err_code = err.get("code") if isinstance(err, dict) else -32000
                            err_msg = err.get("message") if isinstance(err, dict) else str(err)
                            future.set_exception(RuntimeError(f"MCP error {err_code}: {err_msg}"))
                        else:
                            future.set_result(data.get("result", {}))
            except Exception as e:
                logger.debug(f"Error parsing MCP response line: {e}")

    async def close(self) -> None:
        """Shutdown client and terminate process / HTTP session."""
        self._connected = False
        if self._reader_task:
            self._reader_task.cancel()
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        if self._process:
            if self._process.stdin:
                try:
                    self._process.stdin.close()
                except Exception:
                    pass
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except Exception:
                if self._process:
                    self._process.kill()
            self._process = None
        logger.info(f"MCP server '{self.name}' closed")
