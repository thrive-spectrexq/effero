"""Effero device adapters.

This package contains various device adapters for communication with IoT devices, robots, cloud APIs, etc.
"""
from __future__ import annotations

from effero.adapters.base import DeviceAdapter
from effero.adapters.cloud_api.client import CloudAPIAdapter
from effero.adapters.mqtt_matter.client import MockMQTTAdapter, MQTTAdapter, get_default_client
from effero.adapters.ros2.bridge import ROS2Bridge
from effero.adapters.serial_gpio.client import MockSerialAdapter, SerialAdapter

__all__ = [
    "DeviceAdapter",
    "MQTTAdapter",
    "MockMQTTAdapter",
    "get_default_client",
    "SerialAdapter",
    "MockSerialAdapter",
    "CloudAPIAdapter",
    "ROS2Bridge",
]
