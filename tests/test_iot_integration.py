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


@pytest.mark.asyncio
async def test_iot_sensors_and_thermostat_skills():
    """Verify sensors and thermostat skill execution and state management."""
    from effero.adapters.mqtt_matter.client import get_default_client
    from effero.skills.iot.sensors import list_sensors, read_sensor
    from effero.skills.iot.thermostat import get_temperature, set_mode, set_temperature

    client = get_default_client()
    # Populate test state on client
    await client.publish("home/sensors/temp_bedroom/state", 21.5)
    await client.publish("home/sensors/humidity_kitchen/state", 55.0)

    # 1. Read sensor
    read_res = await read_sensor("temp_bedroom")
    assert read_res["status"] == "success"
    assert read_res["value"] == 21.5

    # 2. List sensors
    list_res = await list_sensors()
    assert list_res["status"] == "success"
    assert "temp_bedroom" in list_res["sensors"]
    assert "humidity_kitchen" in list_res["sensors"]

    # 3. Thermostat get default temperature
    t_get = await get_temperature("main_hall")
    assert t_get["status"] == "success"
    assert t_get["temperature"] == 22.0

    # 4. Thermostat set temperature
    t_set = await set_temperature("main_hall", 24.5)
    assert t_set["status"] == "success"
    assert t_set["temperature"] == 24.5

    # 5. Thermostat set mode
    m_set = await set_mode("main_hall", "heat")
    assert m_set["status"] == "success"
    assert m_set["mode"] == "heat"


@pytest.mark.asyncio
async def test_agent_iot_live_broker_connectivity():
    """Test connecting to a live MQTT broker on port 1883 if reachable (e.g. in CI service container)."""
    import asyncio
    import socket

    # Quick TCP probe to check if port 1883 is accepting connections
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        sock.connect(("127.0.0.1", 1883))
        sock.close()
    except (OSError, ConnectionRefusedError):
        sock.close()
        pytest.skip("No live MQTT broker listening on 127.0.0.1:1883")

    cfg = EfferoConfig()
    cfg.iot = IoTConfig(
        enabled=True,
        auto_connect=True,
        broker_host="127.0.0.1",
        broker_port=1883,
    )

    agent = Agent(config=cfg)
    await agent.start()
    try:
        from effero.adapters.mqtt_matter.client import get_default_client

        client = get_default_client(cfg.iot)
        assert client.is_connected is True

        # Test live roundtrip publish and subscribe
        received: list[dict] = []
        await client.subscribe("ci/test/live", lambda t, p: received.append(p))
        await client.publish("ci/test/live", {"msg": "hello from CI", "broker": "mosquitto"})
        await asyncio.sleep(0.1)

        assert len(received) >= 1
        assert received[0]["msg"] == "hello from CI"
    finally:
        await agent.stop()
