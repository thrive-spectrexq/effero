"""Smart light skills."""

from __future__ import annotations

from effero.adapters.mqtt_matter.client import get_default_client
from effero.sdk.skill import SafetyClass, skill


@skill(
    name="iot.lights.toggle",
    description="Toggle light on/off via MQTT",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def toggle(device_id: str, state: str) -> dict:
    client = get_default_client()
    topic = f"home/lights/{device_id}/set"
    payload = {"state": state.upper()}
    await client.publish(topic, payload)
    return {"status": "success", "device_id": device_id, "state": state.upper()}


@skill(
    name="iot.lights.set_brightness",
    description="Set brightness level (0-100)",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def set_brightness(device_id: str, level: int) -> dict:
    client = get_default_client()
    topic = f"home/lights/{device_id}/brightness/set"
    payload = {"brightness": level}
    await client.publish(topic, payload)
    return {"status": "success", "device_id": device_id, "brightness": level}


@skill(
    name="iot.lights.get_status",
    description="Read current light state",
    safety_class=SafetyClass.READ_ONLY,
)
async def get_status(device_id: str) -> dict:
    client = get_default_client()
    state = await client.read_state()
    topic_base = f"home/lights/{device_id}"
    return {
        "status": "success",
        "device_id": device_id,
        "state": state.get(f"{topic_base}/state", "unknown"),
        "brightness": state.get(f"{topic_base}/brightness", "unknown"),
    }
