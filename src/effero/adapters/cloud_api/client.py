"""REST API adapter implementation."""
from __future__ import annotations

import logging
from typing import Any

from effero.adapters.base import DeviceAdapter

logger = logging.getLogger(__name__)

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


class CloudAPIAdapter(DeviceAdapter):
    """Adapter for interacting with RESTful cloud APIs."""

    def __init__(self, base_url: str, headers: dict[str, str] | None = None, auth_token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"
        self._client: Any = None
        self._last_state: dict[str, Any] = {}

    async def connect(self) -> None:
        if not HAS_HTTPX:
            logger.warning("httpx not installed — running cloud API in mock mode")
            return
            
        self._client = httpx.AsyncClient(base_url=self.base_url, headers=self.headers)
        logger.info(f"Cloud API client initialized for {self.base_url}")

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info(f"Cloud API client disconnected from {self.base_url}")

    async def execute(self, command: str, params: dict[str, Any]) -> Any:
        method = params.get("method", "POST").upper()
        endpoint = params.get("endpoint", "")
        payload = params.get("payload")
        
        if self._client:
            response = await self._client.request(method, endpoint, json=payload)
            response.raise_for_status()
            try:
                data = response.json()
            except Exception:
                data = {"text": response.text}
            return data
        else:
            logger.info(f"[Mock API {method}] {self.base_url}/{endpoint.lstrip('/')} -> {payload}")
            return {"status": "mock", "method": method, "endpoint": endpoint}

    async def read_state(self) -> dict[str, Any]:
        if self._client:
            try:
                response = await self._client.get("")
                response.raise_for_status()
                self._last_state = response.json()
            except Exception as e:
                logger.error(f"Failed to read state: {e}")
        return self._last_state
