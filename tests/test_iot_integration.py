"""Tests for IoT MQTT adapter integration in Agent lifecycle."""

import pytest

from effero.config import EfferoConfig, IoTConfig
from effero.core.agent import Agent
from effero.skills.iot.lights import get_status, toggle


@pytest.mark.asyncio
async def test_agent_iot_lifecycle_and_skills():
    """Test Agent initializing with IoT config enabled and executing iot skills."""
    cfg = EfferoConfig()
    cfg.iot = IoTConfig(
        enabled=True,
        auto_connect=False,  # Don't require external broker in test
        broker_host="127.0.0.1",
        broker_port=1883,
    )

    agent = Agent(config=cfg)
    await agent.start()

    try:
        # Skills toggle and get_status operate in memory without network error
        toggle_res = await toggle("living_room", "on")
        assert toggle_res["status"] == "success"
        assert toggle_res["state"] == "ON"

        status_res = await get_status("living_room")
        assert status_res["status"] == "success"
        assert status_res["device_id"] == "living_room"
    finally:
        await agent.stop()
