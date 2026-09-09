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
            req_type = request.get("type")
            if req_type == "heartbeat":
                resp = {"status": "ok", "watchdog_tripped": False}
            elif req_type == "status":
                resp = {"status": "ok", "watchdog": {"tripped": False, "enabled": True}}
            elif req_type == "reset_watchdog":
                resp = {"status": "ok", "watchdog_tripped": False}
            else:
                skill_name = request.get("skill", "")
                resp = decisions.get(skill_name, {"decision": "allow"})
            writer.write((json.dumps(resp) + "\n").encode())
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
async def test_heartbeat_and_status() -> None:
    port = 19403
    server = await _start_safety_kernel_server("127.0.0.1", port, {})

    async with server:
        client = SafetyClient(port=port)
        await client.connect()
        hb = await client.send_heartbeat()
        assert hb["status"] == "ok"
        assert hb["watchdog_tripped"] is False

        status = await client.get_status()
        assert status["status"] == "ok"
        assert status["watchdog"]["tripped"] is False

        reset = await client.reset_watchdog()
        assert reset["status"] == "ok"
        await client.close()


@pytest.mark.asyncio
async def test_connection_refused() -> None:
    client = SafetyClient(port=19499)  # Nothing listening here
    with pytest.raises((ConnectionRefusedError, OSError)):
        await client.connect()
