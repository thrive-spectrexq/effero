"""Browser automation skills powered by Playwright."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from effero.sdk.skill import SafetyClass, skill

logger = logging.getLogger(__name__)


class BrowserController:
    """Manages browser sessions using Playwright with graceful headless fallback."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None

    async def _ensure_page(self) -> Any:
        """Ensure an active browser page exists."""
        if self._page is not None:
            return self._page

        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._page = await self._browser.new_page()
            logger.info("Initialized Playwright real browser instance")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to launch Playwright browser: {exc}. Ensure playwright and browser binaries are installed."
            ) from exc
        return self._page

    async def open_url(self, url: str) -> dict[str, Any]:
        """Navigate to the target URL."""
        if not url.startswith(("http://", "https://", "file://", "about:", "data:")):
            url = f"https://{url}"

        page = await self._ensure_page()
        response = await page.goto(url, wait_until="domcontentloaded")
        title = await page.title()
        status = response.status if response else 200
        return {
            "status": "success",
            "url": page.url,
            "title": title,
            "http_status": status,
        }

    async def screenshot(self, output_path: str = "") -> dict[str, Any]:
        """Capture screenshot of the current page as file or base64."""
        page = await self._ensure_page()
        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(path), full_page=True)
            return {"status": "success", "path": str(path)}

        img_bytes = await page.screenshot(full_page=False)
        b64 = base64.b64encode(img_bytes).decode("ascii")
        return {"status": "success", "image_base64": b64[:100] + "..."}

    async def click(self, selector: str) -> dict[str, Any]:
        """Click an element matching the selector."""
        page = await self._ensure_page()
        await page.click(selector, timeout=5000)
        return {"status": "success", "clicked": selector}

    async def type_text(self, selector: str, text: str) -> dict[str, Any]:
        """Type text into an input element."""
        page = await self._ensure_page()
        await page.fill(selector, text, timeout=5000)
        return {
            "status": "success",
            "selector": selector,
            "text_length": len(text),
        }

    async def get_text(self, selector: str = "body") -> dict[str, Any]:
        """Extract text content from an element."""
        page = await self._ensure_page()
        text = await page.inner_text(selector, timeout=5000)
        return {"status": "success", "selector": selector, "text": text}

    async def close(self) -> dict[str, Any]:
        """Close browser resources."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._page = None
        self._playwright = None
        return {"status": "closed"}


#: Singleton controller instance
_browser_controller = BrowserController()


@skill(
    name="computer_use.browser.open_url",
    description="Navigate the browser to a given URL.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def open_url(url: str) -> dict[str, Any]:
    return await _browser_controller.open_url(url)


@skill(
    name="computer_use.browser.screenshot",
    description="Capture a screenshot of the current browser tab.",
    safety_class=SafetyClass.READ_ONLY,
)
async def screenshot(output_path: str = "") -> dict[str, Any]:
    return await _browser_controller.screenshot(output_path)


@skill(
    name="computer_use.browser.click",
    description="Click a DOM element identified by CSS or XPath selector.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def click(selector: str) -> dict[str, Any]:
    return await _browser_controller.click(selector)


@skill(
    name="computer_use.browser.type_text",
    description="Fill or type text into an input field identified by selector.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def type_text(selector: str, text: str) -> dict[str, Any]:
    return await _browser_controller.type_text(selector, text)


@skill(
    name="computer_use.browser.get_text",
    description="Extract visible text content from a DOM element or entire page.",
    safety_class=SafetyClass.READ_ONLY,
)
async def get_text(selector: str = "body") -> dict[str, Any]:
    return await _browser_controller.get_text(selector)


@skill(
    name="computer_use.browser.close",
    description="Close the active browser tab and session.",
    safety_class=SafetyClass.ACT_AUTONOMOUS,
)
async def close() -> dict[str, Any]:
    return await _browser_controller.close()
