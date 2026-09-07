"""Thermostat skills."""
from __future__ import annotations

from effero.adapters.mqtt_matter.client import get_default_client
from effero.sdk.skill import SafetyClass, skill


@skill(
    name="iot.thermostat.set_temperature",
    description="Set target temperature",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def set_temperature(device_id: str, temperature: float) -> dict:
    client = get_default_client()
    await client.publish(f"home/thermostat/{device_id}/set_temp", {"temperature": temperature})
    return {"status": "success", "device_id": device_id, "temperature": temperature}

@skill(
    name="iot.thermostat.get_temperature",
    description="Read current temperature",
    safety_class=SafetyClass.READ_ONLY,
)
async def get_temperature(device_id: str) -> dict:
    client = get_default_client()
    state = await client.read_state()
    return {
        "status": "success",
        "device_id": device_id,
        "temperature": state.get(f"home/thermostat/{device_id}/current_temp", 22.0)
    }

@skill(
    name="iot.thermostat.set_mode",
    description="Set mode (heat/cool/auto/off)",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def set_mode(device_id: str, mode: str) -> dict:
    client = get_default_client()
    await client.publish(f"home/thermostat/{device_id}/set_mode", {"mode": mode})
    return {"status": "success", "device_id": device_id, "mode": mode}
