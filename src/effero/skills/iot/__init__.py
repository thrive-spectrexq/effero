"""IoT Skills module."""
from __future__ import annotations

from effero.skills.iot.lights import get_status, set_brightness, toggle
from effero.skills.iot.sensors import list_sensors, read_sensor
from effero.skills.iot.thermostat import get_temperature, set_mode, set_temperature

__all__ = [
    "toggle", "set_brightness", "get_status",
    "set_temperature", "get_temperature", "set_mode",
    "read_sensor", "list_sensors"
]
