"""ROS 2 adapter — requires a ROS 2 installation with rclpy."""
from __future__ import annotations

import logging
from typing import Any

from effero.adapters.base import DeviceAdapter

logger = logging.getLogger(__name__)


class ROS2Bridge(DeviceAdapter):
    """Bridge between Effero and ROS 2.
    
    Requires: pip install effero[ros2] and a ROS 2 installation.
    
    This is a stub implementation. Full ROS 2 support is planned for v0.2.
    """

    def __init__(self, node_name: str = "effero_bridge") -> None:
        self.node_name = node_name
        self._node = None
        self._actions: dict[str, str] = {}
        self._topics: dict[str, str] = {}

    async def connect(self) -> None:
        try:
            import rclpy
            rclpy.init()
            self._node = rclpy.create_node(self.node_name)
            logger.info(f"ROS 2 node '{self.node_name}' initialized")
        except ImportError:
            logger.warning("rclpy not installed — ROS 2 bridge running in mock mode")

    async def disconnect(self) -> None:
        if self._node:
            self._node.destroy_node()
            import rclpy
            rclpy.shutdown()

    async def execute(self, command: str, params: dict[str, Any]) -> Any:
        logger.info(f"ROS 2 execute: {command} {params}")
        return {"status": "mock", "command": command}

    async def read_state(self) -> dict[str, Any]:
        return {"node": self.node_name, "status": "mock"}

    def expose_action(self, action_name: str, skill_name: str) -> None:
        self._actions[action_name] = skill_name
        logger.info(f"Exposed ROS 2 action {action_name} as skill {skill_name}")

    def expose_topic(self, topic_name: str, event_name: str) -> None:
        self._topics[topic_name] = event_name
        logger.info(f"Exposed ROS 2 topic {topic_name} as event {event_name}")
