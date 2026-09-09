"""Computer Use Skills module."""

from __future__ import annotations

from effero.skills.computer_use.browser import (
    click,
    close,
    get_text,
    open_url,
    screenshot,
    type_text,
)
from effero.skills.computer_use.desktop import (
    DesktopBackend,
    DesktopController,
    DesktopSafetyError,
    DestructiveHotkeyError,
    DestructiveHotkeyFilter,
    HeadlessDesktopBackend,
    LinuxDesktopBackend,
    SafetyBoundingBox,
    SafetyViolationError,
    Win32DesktopBackend,
    WindowInfo,
    click_mouse,
    desktop_type_text,
    focus_window,
    get_active_window,
    get_cursor_position,
    get_default_desktop_backend,
    get_screen_size,
    list_windows,
    mouse_drag,
    mouse_scroll,
    move_mouse,
    send_hotkey,
    set_safety_bounds,
)
from effero.skills.computer_use.file_ops import list_dir, read_file, write_file
from effero.skills.computer_use.shell import run

__all__ = [
    # Shell & Browser & File
    "run",
    "open_url",
    "screenshot",
    "click",
    "type_text",
    "get_text",
    "close",
    "read_file",
    "write_file",
    "list_dir",
    # Desktop Controller & Models & Backends
    "DesktopBackend",
    "Win32DesktopBackend",
    "LinuxDesktopBackend",
    "HeadlessDesktopBackend",
    "get_default_desktop_backend",
    "DesktopController",
    "WindowInfo",
    "SafetyBoundingBox",
    "DestructiveHotkeyFilter",
    "DesktopSafetyError",
    "SafetyViolationError",
    "DestructiveHotkeyError",
    # Desktop Skills
    "list_windows",
    "get_active_window",
    "focus_window",
    "move_mouse",
    "click_mouse",
    "mouse_drag",
    "mouse_scroll",
    "desktop_type_text",
    "send_hotkey",
    "get_cursor_position",
    "get_screen_size",
    "set_safety_bounds",
]
