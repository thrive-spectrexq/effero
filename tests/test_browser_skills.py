"""Tests for Browser Automation Skill registry contracts."""

from __future__ import annotations

from effero.sdk.skill import SafetyClass, registry


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
