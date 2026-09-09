"""Tests for Browser Automation Skill registry contracts."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from effero.sdk.skill import SafetyClass, registry
from effero.skills.computer_use.browser import (
    click,
    close,
    get_text,
    open_url,
    screenshot,
    type_text,
)


def test_browser_skills_registration() -> None:
    skill_names = registry.list()
    assert "computer_use.browser.open_url" in skill_names
    assert "computer_use.browser.screenshot" in skill_names
    assert "computer_use.browser.click" in skill_names
    assert "computer_use.browser.type_text" in skill_names
    assert "computer_use.browser.get_text" in skill_names
    assert "computer_use.browser.close" in skill_names


def test_browser_skill_safety_contracts() -> None:
    # Verify strict safety classes
    assert registry.get("computer_use.browser.open_url").safety_class == SafetyClass.ACT_WITH_APPROVAL
    assert registry.get("computer_use.browser.click").safety_class == SafetyClass.ACT_WITH_APPROVAL
    assert registry.get("computer_use.browser.type_text").safety_class == SafetyClass.ACT_WITH_APPROVAL
    assert registry.get("computer_use.browser.screenshot").safety_class == SafetyClass.READ_ONLY
    assert registry.get("computer_use.browser.get_text").safety_class == SafetyClass.READ_ONLY
    assert registry.get("computer_use.browser.close").safety_class == SafetyClass.ACT_AUTONOMOUS


@pytest.mark.asyncio
async def test_browser_module_level_skills() -> None:
    """Exercise all exported module-level browser skills against a local DOM."""
    html_content = """
    <html>
      <head><title>Effero Browser Skill Test</title></head>
      <body>
        <h1 id="title">Effero Bot</h1>
        <input id="inp" type="text" />
        <button id="btn" onclick="document.getElementById('title').innerText = 'Clicked!'">Go</button>
      </body>
    </html>
    """
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        tmp.write(html_content)
        temp_file = Path(tmp.name)

    try:
        # 1. open_url
        res = await open_url(temp_file.as_uri())
        assert res["status"] == "success"
        assert res["title"] == "Effero Browser Skill Test"

        # 2. get_text
        t = await get_text("#title")
        assert t["status"] == "success"
        assert t["text"] == "Effero Bot"

        # 3. type_text
        typed = await type_text("#inp", "Automation input")
        assert typed["status"] == "success"
        assert typed["text_length"] == len("Automation input")

        # 4. click
        cl = await click("#btn")
        assert cl["status"] == "success"
        mutated = await get_text("#title")
        assert mutated["text"] == "Clicked!"

        # 5. screenshot to file
        shot_file = temp_file.with_suffix(".png")
        s_file = await screenshot(str(shot_file))
        assert s_file["status"] == "success"
        assert shot_file.exists()
        shot_file.unlink()

        # 6. screenshot in-memory (base64)
        s_b64 = await screenshot()
        assert s_b64["status"] == "success"
        assert "image_base64" in s_b64

        # 7. close
        c = await close()
        assert c["status"] == "closed"
    finally:
        if temp_file.exists():
            temp_file.unlink()
