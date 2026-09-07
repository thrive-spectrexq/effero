"""Browser control skills."""
from __future__ import annotations

import logging

from effero.sdk.skill import SafetyClass, skill

logger = logging.getLogger(__name__)

@skill(
    name="computer_use.browser.open_url",
    description="Open a URL",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def open_url(url: str) -> dict:
    logger.info(f"Mock Browser: Opening {url}")
    return {"status": "success", "action": "open_url", "url": url}

@skill(
    name="computer_use.browser.screenshot",
    description="Take a screenshot",
    safety_class=SafetyClass.READ_ONLY,
)
async def screenshot() -> dict:
    logger.info("Mock Browser: Taking screenshot")
    return {"status": "success", "action": "screenshot", "data": "mock_base64_data"}
