"""Comprehensive automated unit and integration tests for Native Desktop OS automation.

Covers:
- Screen metrics and coordinate mapping (normalized, window-relative, client-to-screen)
- Safety bounding boxes (containment, clamping, window-derived bounds, violations)
- Destructive hotkey filter (blocking forbidden keys, allowing safe combinations)
- Native Win32 window enumeration, search, focus, movement, state manipulation
- Low-level mouse and keyboard input dispatch via SendInput structures
- Skill decorator registration and async skill execution
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Generator

import pytest

import effero.skills.computer_use as cu
from effero.sdk.skill import SafetyClass, registry
from effero.skills.computer_use.desktop import (
    DesktopController,
    DestructiveHotkeyError,
    DestructiveHotkeyFilter,
    SafetyBoundingBox,
    SafetyViolationError,
    WindowInfo,
)

IS_WINDOWS = sys.platform == "win32"


@pytest.fixture
def controller() -> DesktopController:
    """Provide a fresh DesktopController instance."""
    return DesktopController()


@pytest.fixture
def test_window() -> Generator[tuple[int, str], None, None]:
    """Spawn a genuine native Win32 window for integration tests and clean up after."""
    title = f"Effero_Test_Win_{os.getpid()}_{time.time_ns()}"
    class_name = f"EfferoClass_{time.time_ns()}"
    hwnd = 0
    reg = None

    if IS_WINDOWS:
        import win32con
        import win32gui

        wc = win32gui.WNDCLASS()
        wc.lpszClassName = class_name
        wc.lpfnWndProc = win32gui.DefWindowProc
        reg = win32gui.RegisterClass(wc)
        hwnd = win32gui.CreateWindow(
            reg,
            title,
            win32con.WS_OVERLAPPEDWINDOW | win32con.WS_VISIBLE,
            120,
            120,
            400,
            300,
            0,
            0,
            0,
            None,
        )
        win32gui.UpdateWindow(hwnd)

    yield hwnd, title

    if IS_WINDOWS and hwnd:
        import win32gui

        try:
            win32gui.DestroyWindow(hwnd)
            if reg is not None:
                win32gui.UnregisterClass(reg, None)
        except Exception:
            pass


# ============================================================================
# 1. Screen Metrics and Coordinate Mapping Tests
# ============================================================================


def test_screen_size_query(controller: DesktopController) -> None:
    """Verify querying screen dimensions returns positive pixel dimensions."""
    width, height = controller.get_screen_size()
    assert isinstance(width, int)
    assert isinstance(height, int)
    assert width > 0
    assert height > 0


def test_coordinate_mapping_normalized_boundaries(controller: DesktopController) -> None:
    """Verify conversion between normalized [0.0, 1.0] and screen pixels."""
    width, height = controller.get_screen_size()

    # (0.0, 0.0) -> Top-Left (0, 0)
    tl_x, tl_y = controller.normalized_to_screen(0.0, 0.0)
    assert (tl_x, tl_y) == (0, 0)

    # (1.0, 1.0) -> Bottom-Right (width - 1, height - 1)
    br_x, br_y = controller.normalized_to_screen(1.0, 1.0)
    assert (br_x, br_y) == (width - 1, height - 1)

    # (0.5, 0.5) -> Center
    c_x, c_y = controller.normalized_to_screen(0.5, 0.5)
    assert c_x == int(round(0.5 * (width - 1)))
    assert c_y == int(round(0.5 * (height - 1)))

    # Reverse mapping: screen to normalized
    norm_tl_x, norm_tl_y = controller.screen_to_normalized(0, 0)
    assert norm_tl_x == pytest.approx(0.0)
    assert norm_tl_y == pytest.approx(0.0)

    norm_br_x, norm_br_y = controller.screen_to_normalized(width - 1, height - 1)
    assert norm_br_x == pytest.approx(1.0)
    assert norm_br_y == pytest.approx(1.0)


def test_coordinate_mapping_clamping_out_of_range(controller: DesktopController) -> None:
    """Verify normalized conversion clamps values outside [0.0, 1.0]."""
    width, height = controller.get_screen_size()

    x, y = controller.normalized_to_screen(-0.5, 1.5)
    assert x == 0
    assert y == height - 1


def test_window_relative_coordinate_mapping(
    controller: DesktopController,
    test_window: tuple[int, str],
) -> None:
    """Verify window-relative to absolute screen coordinate conversion."""
    hwnd, _title = test_window
    if hwnd == 0:
        pytest.skip("No HWND available in test environment")

    info = controller.get_window_by_hwnd(hwnd)
    assert info is not None

    rel_x, rel_y = 25, 35
    screen_x, screen_y = controller.window_relative_to_screen(hwnd, rel_x, rel_y)
    assert screen_x == info.x + rel_x
    assert screen_y == info.y + rel_y

    roundtrip_rel_x, roundtrip_rel_y = controller.screen_to_window_relative(hwnd, screen_x, screen_y)
    assert roundtrip_rel_x == rel_x
    assert roundtrip_rel_y == rel_y


def test_client_to_screen_mapping(
    controller: DesktopController,
    test_window: tuple[int, str],
) -> None:
    """Verify Win32 ClientToScreen and ScreenToClient conversion."""
    hwnd, _title = test_window
    if hwnd == 0:
        pytest.skip("No HWND available in test environment")

    screen_x, screen_y = controller.client_to_screen(hwnd, 10, 15)
    assert screen_x > 0
    assert screen_y > 0

    client_x, client_y = controller.screen_to_client(hwnd, screen_x, screen_y)
    assert client_x == 10
    assert client_y == 15


# ============================================================================
# 2. Safety Bounding Box Tests
# ============================================================================


def test_safety_bounding_box_containment_and_clamp() -> None:
    """Verify containment logic and clamping on boundary boxes."""
    box = SafetyBoundingBox(min_x=100, min_y=150, max_x=500, max_y=600)

    # Inside
    assert box.contains(250, 300) is True
    assert box.contains(100, 150) is True
    assert box.contains(500, 600) is True

    # Outside
    assert box.contains(99, 300) is False
    assert box.contains(501, 300) is False
    assert box.contains(250, 149) is False
    assert box.contains(250, 601) is False

    # Clamping
    assert box.clamp(50, 50) == (100, 150)
    assert box.clamp(700, 800) == (500, 600)
    assert box.clamp(300, 400) == (300, 400)


def test_safety_bounding_box_validation() -> None:
    """Verify invalid bounding box coordinates raise ValueError."""
    with pytest.raises(ValueError, match="Invalid bounding box"):
        SafetyBoundingBox(min_x=500, min_y=100, max_x=400, max_y=600)


def test_safety_bounding_box_from_real_window(
    test_window: tuple[int, str],
) -> None:
    """Verify deriving a safety bounding box from a live window handle."""
    hwnd, _title = test_window
    if hwnd == 0:
        pytest.skip("No HWND available in test environment")

    box = SafetyBoundingBox.from_window(hwnd)
    assert box.max_x > box.min_x
    assert box.max_y > box.min_y
    # Inside window
    assert box.contains(box.min_x + 5, box.min_y + 5) is True
    # Outside window
    assert box.contains(box.min_x - 50, box.min_y - 50) is False


def test_safety_bounds_raise_policy_enforcement(controller: DesktopController) -> None:
    """Verify move_mouse raises SafetyViolationError when out of bounds under 'raise' policy."""
    box = SafetyBoundingBox(min_x=100, min_y=100, max_x=300, max_y=300)
    controller.set_safety_bounds(box, policy="raise")

    # Inside bounds succeeds
    pos = controller.move_mouse(150, 150, smooth=False)
    assert pos == (150, 150)

    # Outside bounds raises
    with pytest.raises(SafetyViolationError, match="outside safety bounds"):
        controller.move_mouse(500, 500, smooth=False)


def test_safety_bounds_clamp_policy_enforcement(controller: DesktopController) -> None:
    """Verify move_mouse clamps coordinates when out of bounds under 'clamp' policy."""
    box = SafetyBoundingBox(min_x=100, min_y=100, max_x=300, max_y=300)
    controller.set_safety_bounds(box, policy="clamp")

    pos = controller.move_mouse(500, 600, smooth=False)
    assert pos == (300, 300)
    assert controller.get_cursor_position() == (300, 300)


# ============================================================================
# 3. Destructive Hotkey Filter Tests
# ============================================================================


def test_destructive_hotkey_filter_blocks_forbidden() -> None:
    """Verify the filter blocks Alt+F4, Ctrl+Alt+Del, Win+L, Ctrl+Shift+Esc, Ctrl+W, Alt+Space+C."""
    hk_filter = DestructiveHotkeyFilter()

    # Variations of forbidden hotkeys
    forbidden_samples: list[str | list[str]] = [
        "Alt+F4",
        "alt+f4",
        ["alt", "f4"],
        ["ALT", "F4"],
        "Ctrl+Alt+Del",
        "control+alt+delete",
        ["ctrl", "alt", "del"],
        ["control", "alt", "delete"],
        "Win+L",
        "windows+l",
        ["win", "l"],
        ["super", "l"],
        "Ctrl+Shift+Esc",
        ["ctrl", "shift", "escape"],
        "Ctrl+W",
        "control+w",
        ["ctrl", "w"],
        "Alt+Space+C",
        ["alt", "space", "c"],
        ["menu", "spc", "c"],
    ]

    for sample in forbidden_samples:
        assert hk_filter.is_destructive(sample) is True, f"Failed to detect destructive: {sample}"
        with pytest.raises(DestructiveHotkeyError, match="Destructive hotkey blocked"):
            hk_filter.validate(sample)


def test_destructive_hotkey_filter_allows_safe_combinations() -> None:
    """Verify the filter permits standard non-destructive shortcuts."""
    hk_filter = DestructiveHotkeyFilter()

    safe_samples: list[str | list[str]] = [
        "Ctrl+C",
        "Ctrl+V",
        "Ctrl+Z",
        "Ctrl+A",
        "Ctrl+S",
        "Alt+Tab",
        ["ctrl", "shift", "t"],
        ["win", "r"],
        ["enter"],
        "space",
    ]

    for sample in safe_samples:
        assert hk_filter.is_destructive(sample) is False, f"False positive on safe key: {sample}"
        hk_filter.validate(sample)  # Does not raise


def test_controller_send_hotkey_rejects_destructive(controller: DesktopController) -> None:
    """Verify DesktopController.send_hotkey raises DestructiveHotkeyError on destructive inputs."""
    with pytest.raises(DestructiveHotkeyError):
        controller.send_hotkey(["alt", "f4"])

    with pytest.raises(DestructiveHotkeyError):
        controller.send_hotkey(["ctrl", "alt", "del"])

    with pytest.raises(DestructiveHotkeyError):
        controller.send_hotkey(["ctrl", "w"])


# ============================================================================
# 4. Window Management and Enumeration Tests
# ============================================================================


def test_window_enumeration_with_real_window(
    controller: DesktopController,
    test_window: tuple[int, str],
) -> None:
    """Verify EnumWindows finds the test window with correct title, HWND, and PID."""
    hwnd, title = test_window
    if hwnd == 0:
        pytest.skip("No HWND available in test environment")

    windows = controller.list_windows(visible_only=True)
    assert len(windows) > 0

    found = next((w for w in windows if w.hwnd == hwnd), None)
    assert found is not None
    assert found.title == title
    assert found.width > 0
    assert found.height > 0
    assert found.process_id == os.getpid()


def test_window_lookup_by_title_and_hwnd(
    controller: DesktopController,
    test_window: tuple[int, str],
) -> None:
    """Verify window lookup by title substring and by exact HWND handle."""
    hwnd, title = test_window
    if hwnd == 0:
        pytest.skip("No HWND available in test environment")

    # Lookup by title substring
    by_title = controller.get_window_by_title(title[:15])
    assert by_title is not None
    assert by_title.hwnd == hwnd

    # Lookup by exact HWND
    by_hwnd = controller.get_window_by_hwnd(hwnd)
    assert by_hwnd is not None
    assert by_hwnd.title == title
    assert by_hwnd.hwnd == hwnd


def test_window_focus_and_geometry_manipulation(
    controller: DesktopController,
    test_window: tuple[int, str],
) -> None:
    """Verify window focus, minimize, restore, and move operations."""
    hwnd, _title = test_window
    if hwnd == 0:
        pytest.skip("No HWND available in test environment")

    # Focus window
    focused = controller.focus_window(hwnd)
    assert focused is True

    # Move and resize window
    moved = controller.move_window(hwnd, 150, 160, 420, 320, repaint=True)
    assert moved is True

    updated_info = controller.get_window_by_hwnd(hwnd)
    assert updated_info is not None
    assert updated_info.x == 150
    assert updated_info.y == 160

    # Minimize and restore
    minimized = controller.minimize_window(hwnd)
    assert minimized is True

    restored = controller.restore_window(hwnd)
    assert restored is True


def test_window_info_dataclass() -> None:
    """Verify WindowInfo dataclass serialization to dictionary."""
    win = WindowInfo(
        hwnd=12345,
        title="Test Window",
        x=10,
        y=20,
        width=300,
        height=200,
        is_active=True,
        process_id=999,
    )
    d = win.to_dict()
    assert d["hwnd"] == 12345
    assert d["title"] == "Test Window"
    assert d["x"] == 10
    assert d["y"] == 20
    assert d["width"] == 300
    assert d["height"] == 200
    assert d["is_active"] is True
    assert d["process_id"] == 999


# ============================================================================
# 5. Low-Level Input Dispatch Tests
# ============================================================================


def test_mouse_movement_and_cursor_tracking(controller: DesktopController) -> None:
    """Verify mouse positioning and smooth interpolation."""
    pos1 = controller.move_mouse(120, 140, smooth=False)
    assert pos1 == (120, 140)
    assert controller.get_cursor_position() == (120, 140)

    # Smooth movement
    pos2 = controller.move_mouse(200, 220, smooth=True, steps=5)
    assert pos2 == (200, 220)
    assert controller.get_cursor_position() == (200, 220)


def test_mouse_actions_dispatch(controller: DesktopController) -> None:
    """Verify click, double-click, drag, and scroll dispatch."""
    controller.move_mouse(150, 150, smooth=False)

    # Left, right, middle click
    controller.click_mouse(button="left", clicks=1, interval=0.01)
    controller.click_mouse(button="right", clicks=1, interval=0.01)
    controller.click_mouse(button="middle", clicks=1, interval=0.01)

    # Double click
    controller.double_click(button="left")

    # Drag
    controller.mouse_drag(100, 100, 200, 200, button="left", steps=3)
    assert controller.get_cursor_position() == (200, 200)

    # Scroll up and down
    controller.mouse_scroll(clicks=1, direction="up")
    controller.mouse_scroll(clicks=2, direction="down")


def test_keyboard_unicode_typing_and_press(controller: DesktopController) -> None:
    """Verify typing unicode characters and pressing keys."""
    # Unicode text typing
    controller.type_text("Effero AI 2026! 🚀")

    # Standard key presses
    controller.press_key("enter")
    controller.press_key("tab")
    controller.press_key("space")
    controller.press_key("backspace")

    # Unknown key raises ValueError
    with pytest.raises(ValueError, match="Unsupported virtual key"):
        controller.press_key("nonexistent_super_key_xyz")


def test_send_safe_hotkey(controller: DesktopController) -> None:
    """Verify dispatching safe hotkey combinations."""
    controller.send_hotkey(["ctrl", "c"])
    controller.send_hotkey(["shift", "tab"])


# ============================================================================
# 6. Skill Registration and Async Wrapper Tests
# ============================================================================


def test_desktop_skills_registered_in_registry() -> None:
    """Verify all 12 desktop skills are registered with appropriate SafetyClass."""
    expected_skills = {
        "computer_use.desktop.list_windows": SafetyClass.READ_ONLY,
        "computer_use.desktop.get_active_window": SafetyClass.READ_ONLY,
        "computer_use.desktop.focus_window": SafetyClass.ACT_WITH_APPROVAL,
        "computer_use.desktop.move_mouse": SafetyClass.ACT_WITH_APPROVAL,
        "computer_use.desktop.click_mouse": SafetyClass.ACT_WITH_APPROVAL,
        "computer_use.desktop.mouse_drag": SafetyClass.ACT_WITH_APPROVAL,
        "computer_use.desktop.mouse_scroll": SafetyClass.ACT_WITH_APPROVAL,
        "computer_use.desktop.type_text": SafetyClass.ACT_WITH_APPROVAL,
        "computer_use.desktop.send_hotkey": SafetyClass.ACT_WITH_APPROVAL,
        "computer_use.desktop.get_cursor_position": SafetyClass.READ_ONLY,
        "computer_use.desktop.get_screen_size": SafetyClass.READ_ONLY,
        "computer_use.desktop.set_safety_bounds": SafetyClass.ACT_WITH_APPROVAL,
    }

    registered_skills = registry.list()
    for skill_name, safety_class in expected_skills.items():
        assert skill_name in registered_skills, f"Missing registered skill: {skill_name}"
        spec = registry.get(skill_name)
        assert spec.safety_class == safety_class, f"Mismatch safety class for {skill_name}"


@pytest.mark.asyncio
async def test_async_skill_execution() -> None:
    """Verify executing async skill wrappers returns formatted success dictionaries."""
    # Screen size
    screen_res = await cu.get_screen_size()
    assert screen_res["status"] == "success"
    assert screen_res["width"] > 0
    assert screen_res["height"] > 0

    # Set safety bounds
    bounds_res = await cu.set_safety_bounds(0, 0, screen_res["width"], screen_res["height"])
    assert bounds_res["status"] == "success"

    # Move mouse
    move_res = await cu.move_mouse(100, 100, smooth=False)
    assert move_res["status"] == "success"
    assert move_res["cursor"] == {"x": 100, "y": 100}

    # Click mouse
    click_res = await cu.click_mouse(button="left", clicks=1)
    assert click_res["status"] == "success"

    # Type text
    type_res = await cu.desktop_type_text("Effero Automation")
    assert type_res["status"] == "success"
    assert type_res["characters_typed"] == len("Effero Automation")

    # Send hotkey
    hotkey_res = await cu.send_hotkey(["ctrl", "c"])
    assert hotkey_res["status"] == "success"

    # List windows
    wins_res = await cu.list_windows()
    assert wins_res["status"] == "success"
    assert isinstance(wins_res["windows"], list)


def test_controller_clamp_policy(controller: DesktopController) -> None:
    """Verify that clamp safety policy restricts coordinates without raising."""
    box = SafetyBoundingBox(min_x=100, min_y=100, max_x=500, max_y=500)
    controller.set_safety_bounds(box, policy="clamp")
    assert controller.get_safety_bounds() == box

    # Moving to 50, 50 clamps to 100, 100
    res = controller.set_cursor_position(50, 50)
    assert res == (100, 100)

    # Moving to 600, 700 clamps to 500, 500
    res2 = controller.set_cursor_position(600, 700)
    assert res2 == (500, 500)

    # Reset
    controller.set_safety_bounds(None)


def test_controller_mouse_and_key_actions(controller: DesktopController) -> None:
    """Verify low-level mouse actions (double_click, right_click, scroll, drag)."""
    # Mouse movements and clicks
    controller.set_cursor_position(200, 200)
    controller.double_click(button="left")
    controller.click_mouse(button="right")
    controller.mouse_scroll(clicks=2, direction="up")
    controller.mouse_scroll(clicks=2, direction="down")
    controller.mouse_drag(200, 200, 210, 210, button="left", steps=2)

    # Mouse down and up
    controller.mouse_down("left")
    controller.mouse_up("left")

    # Keyboard down and up
    controller.key_down("shift")
    controller.key_up("shift")
    controller.type_text("Hello Effero")


def test_controller_window_geometry_transforms(controller: DesktopController) -> None:
    """Verify screen to client and relative conversions with mock and real HWND."""
    # Test screen to client and client to screen identity or offset
    s_x, s_y = controller.client_to_screen(0, 50, 50)
    assert isinstance(s_x, int) and isinstance(s_y, int)

    c_x, c_y = controller.screen_to_client(0, s_x, s_y)
    assert isinstance(c_x, int) and isinstance(c_y, int)
