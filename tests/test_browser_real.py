"""Tests for REAL Playwright browser automation skills (no mocks or stubs)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from effero.skills.computer_use.browser import BrowserController


@pytest.mark.asyncio
async def test_real_browser_automation() -> None:
    controller = BrowserController(headless=True)

    html_content = """
    <html>
      <head><title>Effero Automation Real Page</title></head>
      <body>
        <h1 id="header">Effero Robotics & AI</h1>
        <input id="search-box" type="text" />
        <button id="action-btn" onclick="document.getElementById('header').innerText = 'Action Triggered!'">Submit</button>
      </body>
    </html>
    """

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        tmp.write(html_content)
        tmp_path = tmp.name

    try:
        file_url = Path(tmp_path).as_uri()

        # 1. Open URL
        open_res = await controller.open_url(file_url)
        assert open_res["status"] == "success"
        assert open_res["title"] == "Effero Automation Real Page"

        # 2. Extract real DOM text
        header_text = await controller.get_text("#header")
        assert header_text["status"] == "success"
        assert header_text["text"] == "Effero Robotics & AI"

        # 3. Type real text into input field
        type_res = await controller.type_text("#search-box", "Real autonomous agent test")
        assert type_res["status"] == "success"
        assert type_res["text_length"] == len("Real autonomous agent test")

        # 4. Click button and verify live DOM mutation
        click_res = await controller.click("#action-btn")
        assert click_res["status"] == "success"
        mutated_text = await controller.get_text("#header")
        assert mutated_text["text"] == "Action Triggered!"

        # 5. Capture real full-page screenshot
        screenshot_path = Path(tmp_path).with_suffix(".png")
        shot_res = await controller.screenshot(output_path=str(screenshot_path))
        assert shot_res["status"] == "success"
        assert screenshot_path.exists()
        # Verify valid PNG header (0x89 0x50 0x4E 0x47)
        with open(screenshot_path, "rb") as f:
            header_bytes = f.read(4)
            assert header_bytes == b"\x89PNG"

        if screenshot_path.exists():
            screenshot_path.unlink()

        # 6. Close browser
        close_res = await controller.close()
        assert close_res["status"] == "closed"

    finally:
        if Path(tmp_path).exists():
            Path(tmp_path).unlink()
