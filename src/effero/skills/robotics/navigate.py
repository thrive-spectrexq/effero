"""Robot Navigation Skills."""
from __future__ import annotations

import logging

from effero.sdk.skill import SafetyClass, skill

logger = logging.getLogger(__name__)

@skill(
    name="robotics.navigate.go_to",
    description="Navigate to waypoint",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def go_to(waypoint: str) -> dict:
    logger.info(f"Mock Navigation: Going to {waypoint}")
    return {"status": "success", "action": "go_to", "waypoint": waypoint}

@skill(
    name="robotics.navigate.stop",
    description="Emergency stop",
    safety_class=SafetyClass.ACT_AUTONOMOUS,
)
async def stop() -> dict:
    logger.info("Mock Navigation: Emergency stop triggered")
    return {"status": "success", "action": "stop"}

@skill(
    name="robotics.navigate.get_position",
    description="Get current position",
    safety_class=SafetyClass.READ_ONLY,
)
async def get_position() -> dict:
    logger.info("Mock Navigation: Getting position")
    return {"status": "success", "action": "get_position", "position": [0.0, 0.0, 0.0]}
