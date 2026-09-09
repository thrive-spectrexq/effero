"""Tests for SafetyClient."""

from __future__ import annotations

import asyncio
import json

import pytest

from effero.safety.client import SafetyClient


async def _start_safety_kernel_server(host: str, port: int, decisions: dict) -> asyncio.AbstractServer:
    """Start an in-process safety kernel TCP server."""

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        while True:
            line = await reader.readline()
            if not line:
                break
            request = json.loads(line.decode())
            skill_name = request.get("skill", "")
            decision = decisions.get(skill_name, {"decision": "allow"})
            writer.write((json.dumps(decision) + "\n").encode())
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle_client, host, port)
    return server


@pytest.mark.asyncio
async def test_connect_and_check_allow() -> None:
    port = 19401
    decisions = {"test.skill": {"decision": "allow"}}
    server = await _start_safety_kernel_server("127.0.0.1", port, decisions)

    async with server:
        client = SafetyClient(port=port)
        await client.connect()
        result = await client.check_action("test.skill")
        assert result["decision"] == "allow"
        await client.close()


@pytest.mark.asyncio
async def test_check_deny() -> None:
    port = 19402
    decisions = {"dangerous.skill": {"decision": "deny", "reason": "Too risky"}}
    server = await _start_safety_kernel_server("127.0.0.1", port, decisions)

    async with server:
        client = SafetyClient(port=port)
        await client.connect()
        result = await client.check_action("dangerous.skill")
        assert result["decision"] == "deny"
        assert "risky" in result["reason"].lower()
        await client.close()


@pytest.mark.asyncio
async def test_connection_refused() -> None:
    client = SafetyClient(port=19499)  # Nothing listening here
    with pytest.raises((ConnectionRefusedError, OSError)):
        await client.connect()
