"""Effero device adapters.

This package contains various device adapters for communication with IoT devices, robots, cloud APIs, etc.
"""

from __future__ import annotations

from effero.adapters.base import DeviceAdapter
from effero.adapters.cloud_api.client import CloudAPIAdapter
from effero.adapters.mqtt_matter.client import MQTTAdapter, get_default_client
from effero.adapters.ros2.bridge import ROS2Bridge
from effero.adapters.serial_gpio.client import SerialAdapter

__all__ = [
    "DeviceAdapter",
    "MQTTAdapter",
    "get_default_client",
    "SerialAdapter",
    "CloudAPIAdapter",
    "ROS2Bridge",
]
