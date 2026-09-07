"""MQTT adapter implementation."""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from effero.adapters.base import DeviceAdapter

logger = logging.getLogger(__name__)

try:
    import aiomqtt
    HAS_AIOMQTT = True
except ImportError:
    HAS_AIOMQTT = False


class MQTTAdapter(DeviceAdapter):
    """MQTT Adapter for pub/sub messaging."""

    def __init__(self, broker_host: str = "localhost", broker_port: int = 1883, username: str | None = None, password: str | None = None) -> None:
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self._client: Any = None
        self._state: dict[str, Any] = {}

    async def connect(self) -> None:
        if not HAS_AIOMQTT:
            logger.warning("aiomqtt not installed — using mock MQTT adapter")
            return
        
        self._client = aiomqtt.Client(
            hostname=self.broker_host, 
            port=self.broker_port,
            username=self.username,
            password=self.password
        )
        await self._client.connect()
        logger.info(f"Connected to MQTT broker at {self.broker_host}:{self.broker_port}")

    async def disconnect(self) -> None:
        if self._client:
            await self._client.disconnect()
            self._client = None
            logger.info("Disconnected from MQTT broker")

    async def execute(self, command: str, params: dict[str, Any]) -> Any:
        topic = params.get("topic")
        payload = params.get("payload", {})
        if not topic:
            raise ValueError("execute requires 'topic' in params")
        await self.publish(topic, payload)
        return {"status": "success", "command": command, "topic": topic}

    async def read_state(self) -> dict[str, Any]:
        return self._state

    async def publish(self, topic: str, payload: Any) -> None:
        if self._client:
            payload_str = json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)
            await self._client.publish(topic, payload_str)
        else:
            logger.info(f"[Mock MQTT Publish] {topic}: {payload}")
            self._state[topic] = payload

    async def subscribe(self, topic: str, callback: Callable[[str, Any], Awaitable[None]]) -> None:
        if self._client:
            await self._client.subscribe(topic)
            logger.info(f"Subscribed to {topic}")
        else:
            logger.info(f"[Mock MQTT Subscribe] {topic}")


class MockMQTTAdapter(MQTTAdapter):
    """Mock MQTT Adapter for testing and fallback."""

    async def connect(self) -> None:
        logger.info(f"Mock connected to {self.broker_host}:{self.broker_port}")

    async def disconnect(self) -> None:
        logger.info("Mock disconnected")

    async def publish(self, topic: str, payload: Any) -> None:
        logger.info(f"[Mock MQTT Publish] {topic}: {payload}")
        self._state[topic] = payload


_default_client: MQTTAdapter | None = None

def get_default_client() -> MQTTAdapter:
    global _default_client
    if _default_client is None:
        _default_client = MQTTAdapter() if HAS_AIOMQTT else MockMQTTAdapter()
    return _default_client
