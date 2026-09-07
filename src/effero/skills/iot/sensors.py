"""Sensor reading skills."""

from __future__ import annotations

from effero.adapters.mqtt_matter.client import get_default_client
from effero.sdk.skill import SafetyClass, skill


@skill(
    name="iot.sensors.read",
    description="Read a named sensor's current value",
    safety_class=SafetyClass.READ_ONLY,
)
async def read_sensor(sensor_id: str) -> dict:
    client = get_default_client()
    state = await client.read_state()
    val = state.get(f"home/sensors/{sensor_id}/state", None)
    return {"status": "success", "sensor_id": sensor_id, "value": val}


@skill(
    name="iot.sensors.list",
    description="List available sensors",
    safety_class=SafetyClass.READ_ONLY,
)
async def list_sensors() -> dict:
    client = get_default_client()
    state = await client.read_state()
    sensors = [k.split("/")[2] for k in state.keys() if k.startswith("home/sensors/")]
    return {"status": "success", "sensors": list(set(sensors))}
