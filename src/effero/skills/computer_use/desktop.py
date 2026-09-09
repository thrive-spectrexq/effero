"""Native Desktop OS automation skill module supporting Windows, Linux, and headless runtimes."""

from __future__ import annotations

import ctypes
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from effero.sdk.skill import SafetyClass, skill
from effero.skills.computer_use.backends import (
    IS_WINDOWS,
    RECT,
    DesktopBackend,
    HeadlessDesktopBackend,
    LinuxDesktopBackend,
    Win32DesktopBackend,
    WindowInfo,
    get_default_desktop_backend,
    user32,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DesktopBackend",
    "Win32DesktopBackend",
    "LinuxDesktopBackend",
    "HeadlessDesktopBackend",
    "get_default_desktop_backend",
    "WindowInfo",
    "SafetyBoundingBox",
    "DestructiveHotkeyFilter",
    "DesktopSafetyError",
    "SafetyViolationError",
    "DestructiveHotkeyError",
    "DesktopController",
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


# ============================================================================
# Safety and Exception Classes
# ============================================================================


class DesktopSafetyError(Exception):
    """Base exception for desktop OS automation safety errors."""


class SafetyViolationError(DesktopSafetyError):
    """Raised when coordinates or actions violate configured safety bounds."""


class DestructiveHotkeyError(DesktopSafetyError):
    """Raised when a forbidden destructive hotkey combination is requested."""


# ============================================================================
# Data Models and Safety Filters
# ============================================================================


@dataclass(frozen=True)
class SafetyBoundingBox:
    """Defines coordinate boundaries to prevent cursor escape."""

    min_x: int
    min_y: int
    max_x: int
    max_y: int

    def __post_init__(self) -> None:
        if self.min_x > self.max_x or self.min_y > self.max_y:
            raise ValueError(f"Invalid bounding box: ({self.min_x}, {self.min_y}) to ({self.max_x}, {self.max_y})")

    def contains(self, x: int, y: int) -> bool:
        """Check if (x, y) falls inside or on the boundary of the box."""
        return self.min_x <= x <= self.max_x and self.min_y <= y <= self.max_y

    def clamp(self, x: int, y: int) -> tuple[int, int]:
        """Clamp coordinates to the nearest boundary edge."""
        clamped_x = max(self.min_x, min(x, self.max_x))
        clamped_y = max(self.min_y, min(y, self.max_y))
        return clamped_x, clamped_y

    @classmethod
    def from_window(cls, hwnd: int, backend: DesktopBackend | None = None) -> SafetyBoundingBox:
        """Derive bounding box from a live window handle."""
        b = backend or (_controller.backend if "_controller" in globals() else None)
        if b is not None:
            rect = b.get_window_rect(hwnd)
            if rect is not None:
                return cls(min_x=rect[0], min_y=rect[1], max_x=rect[2], max_y=rect[3])
        if IS_WINDOWS and user32 is not None:
            rect_st = RECT()
            res = user32.GetWindowRect(hwnd, ctypes.byref(rect_st))
            if res:
                return cls(min_x=rect_st.left, min_y=rect_st.top, max_x=rect_st.right, max_y=rect_st.bottom)
        raise RuntimeError(f"Failed to query window bounds for handle {hwnd}")

    @classmethod
    def full_screen(cls, width: int, height: int) -> SafetyBoundingBox:
        """Construct bounding box covering the entire primary screen."""
        return cls(min_x=0, min_y=0, max_x=max(0, width - 1), max_y=max(0, height - 1))


class DestructiveHotkeyFilter:
    """Filters and intercepts destructive OS hotkey combinations."""

    KEY_ALIASES: dict[str, str] = {
        "control": "ctrl",
        "ctl": "ctrl",
        "del": "delete",
        "esc": "escape",
        "windows": "win",
        "super": "win",
        "meta": "win",
        "return": "enter",
        "menu": "alt",
        "spc": "space",
    }

    # Forbidden combinations defined in R1
    DEFAULT_BLOCKED: tuple[frozenset[str], ...] = (
        frozenset({"alt", "f4"}),
        frozenset({"ctrl", "alt", "delete"}),
        frozenset({"win", "l"}),
        frozenset({"ctrl", "shift", "escape"}),
        frozenset({"ctrl", "w"}),
        frozenset({"alt", "space", "c"}),
    )

    def __init__(self, additional_blocked: list[set[str]] | None = None) -> None:
        blocked_list = list(self.DEFAULT_BLOCKED)
        if additional_blocked:
            for item in additional_blocked:
                normalized = {self.normalize_key(k) for k in item}
                blocked_list.append(frozenset(normalized))
        self.blocked_combinations: tuple[frozenset[str], ...] = tuple(blocked_list)

    @classmethod
    def normalize_key(cls, key: str) -> str:
        """Normalize key name to lowercase canonical token."""
        cleaned = key.strip().lower()
        return cls.KEY_ALIASES.get(cleaned, cleaned)

    @classmethod
    def normalize_combination(cls, keys: str | Sequence[str]) -> set[str]:
        """Convert key sequence or delimited string into a canonical token set."""
        if isinstance(keys, str):
            parts = re.split(r"[+\-\s]+", keys.strip())
        else:
            parts = []
            for item in keys:
                parts.extend(re.split(r"[+\-\s]+", item.strip()))
        return {cls.normalize_key(p) for p in parts if p}

    def is_destructive(self, keys: str | Sequence[str]) -> bool:
        """Return True if the hotkey combination matches any blocked rule."""
        combo = self.normalize_combination(keys)
        for blocked in self.blocked_combinations:
            if blocked.issubset(combo):
                return True
        return False

    def validate(self, keys: str | Sequence[str]) -> None:
        """Raise DestructiveHotkeyError if combination is forbidden."""
        if self.is_destructive(keys):
            combo_str = "+".join(sorted(self.normalize_combination(keys)))
            raise DestructiveHotkeyError(f"Destructive hotkey blocked by safety policy: {combo_str}")


# ============================================================================
# Desktop Controller Implementation
# ============================================================================


class DesktopController:
    """Manages cross-platform desktop automation, coordinate conversion, and safety policies."""

    def __init__(
        self,
        safety_bounds: SafetyBoundingBox | None = None,
        safety_policy: str = "raise",
        hotkey_filter: DestructiveHotkeyFilter | None = None,
        backend: DesktopBackend | None = None,
    ) -> None:
        self._backend: DesktopBackend = backend or get_default_desktop_backend()
        self._safety_bounds: SafetyBoundingBox | None = safety_bounds
        self._safety_policy: str = safety_policy.lower()  # "raise" or "clamp"
        self._hotkey_filter: DestructiveHotkeyFilter = hotkey_filter or DestructiveHotkeyFilter()

        # Track internal cursor position
        self._cursor_pos: tuple[int, int] = self._backend.get_cursor_position()

    @property
    def backend(self) -> DesktopBackend:
        """Return the underlying DesktopBackend instance."""
        return self._backend

    # ------------------------------------------------------------------------
    # Safety Configuration
    # ------------------------------------------------------------------------

    def set_safety_bounds(
        self,
        bounds: SafetyBoundingBox | None,
        policy: str = "raise",
    ) -> None:
        """Set or remove active safety bounding box and enforcement policy."""
        if policy not in ("raise", "clamp"):
            raise ValueError(f"Invalid safety policy '{policy}'. Must be 'raise' or 'clamp'.")
        self._safety_bounds = bounds
        self._safety_policy = policy

    def set_safety_bounds_from_window(self, hwnd: int, policy: str = "raise") -> None:
        """Constrain cursor safety bounding box to a specific window."""
        box = SafetyBoundingBox.from_window(hwnd, backend=self._backend)
        self.set_safety_bounds(box, policy=policy)

    def get_safety_bounds(self) -> SafetyBoundingBox | None:
        """Retrieve current safety bounding box."""
        return self._safety_bounds

    def _enforce_safety_bounds(self, x: int, y: int) -> tuple[int, int]:
        """Verify (x, y) against active bounding box, raising or clamping based on policy."""
        if self._safety_bounds is None:
            return x, y

        if not self._safety_bounds.contains(x, y):
            if self._safety_policy == "raise":
                raise SafetyViolationError(f"Target coordinate ({x}, {y}) outside safety bounds {self._safety_bounds}")
            # Clamping policy
            return self._safety_bounds.clamp(x, y)
        return x, y

    # ------------------------------------------------------------------------
    # Coordinate Mapping and Screen Metrics
    # ------------------------------------------------------------------------

    def get_screen_size(self) -> tuple[int, int]:
        """Query primary screen dimensions (width, height) in pixels."""
        return self._backend.get_screen_size()

    def get_cursor_position(self) -> tuple[int, int]:
        """Query current cursor position (x, y)."""
        self._cursor_pos = self._backend.get_cursor_position()
        return self._cursor_pos

    def set_cursor_position(self, x: int, y: int) -> tuple[int, int]:
        """Directly position the cursor to (x, y) after safety check."""
        target_x, target_y = self._enforce_safety_bounds(x, y)
        self._cursor_pos = self._backend.set_cursor_position(target_x, target_y)
        return self._cursor_pos

    def client_to_screen(self, hwnd: int, client_x: int, client_y: int) -> tuple[int, int]:
        """Convert client-area relative coordinates to absolute screen pixels."""
        return self._backend.client_to_screen(hwnd, client_x, client_y)

    def screen_to_client(self, hwnd: int, screen_x: int, screen_y: int) -> tuple[int, int]:
        """Convert absolute screen pixel coordinates to client-area coordinates."""
        return self._backend.screen_to_client(hwnd, screen_x, screen_y)

    def normalized_to_screen(self, norm_x: float, norm_y: float) -> tuple[int, int]:
        """Convert normalized [0.0, 1.0] coordinates to absolute screen pixels."""
        width, height = self.get_screen_size()
        clamped_norm_x = max(0.0, min(1.0, float(norm_x)))
        clamped_norm_y = max(0.0, min(1.0, float(norm_y)))
        pixel_x = int(round(clamped_norm_x * (width - 1)))
        pixel_y = int(round(clamped_norm_y * (height - 1)))
        return pixel_x, pixel_y

    def screen_to_normalized(self, pixel_x: int, pixel_y: int) -> tuple[float, float]:
        """Convert absolute screen pixels to normalized [0.0, 1.0] coordinates."""
        width, height = self.get_screen_size()
        norm_x = max(0.0, min(1.0, pixel_x / max(1, width - 1)))
        norm_y = max(0.0, min(1.0, pixel_y / max(1, height - 1)))
        return norm_x, norm_y

    def window_relative_to_screen(self, hwnd: int, rel_x: int, rel_y: int) -> tuple[int, int]:
        """Convert window-relative coordinates (origin at window top-left) to absolute screen coordinates."""
        rect = self._backend.get_window_rect(hwnd)
        if rect is None:
            raise RuntimeError(f"Could not retrieve window rect for handle {hwnd}")
        return rect[0] + rel_x, rect[1] + rel_y

    def screen_to_window_relative(self, hwnd: int, screen_x: int, screen_y: int) -> tuple[int, int]:
        """Convert absolute screen coordinates to window-relative coordinates."""
        rect = self._backend.get_window_rect(hwnd)
        if rect is None:
            raise RuntimeError(f"Could not retrieve window rect for handle {hwnd}")
        return screen_x - rect[0], screen_y - rect[1]

    # ------------------------------------------------------------------------
    # Window Management
    # ------------------------------------------------------------------------

    def list_windows(self, visible_only: bool = True) -> list[WindowInfo]:
        """Enumerate top-level OS windows and extract their geometry and metadata."""
        return self._backend.list_windows(visible_only=visible_only)

    def get_active_window(self) -> WindowInfo | None:
        """Retrieve metadata for the currently active foreground window."""
        return self._backend.get_active_window()

    def get_window_by_hwnd(self, hwnd: int) -> WindowInfo | None:
        """Query window metadata by its handle / ID."""
        return self._backend.get_window_by_hwnd(hwnd)

    def get_window_by_title(self, title_query: str) -> WindowInfo | None:
        """Find the first window matching title substring (case-insensitive)."""
        return self._backend.get_window_by_title(title_query)

    def focus_window(self, identifier: str | int) -> bool:
        """Bring window to foreground and give it focus."""
        return self._backend.focus_window(identifier)

    def minimize_window(self, identifier: str | int) -> bool:
        """Minimize the target window."""
        return self._backend.minimize_window(identifier)

    def maximize_window(self, identifier: str | int) -> bool:
        """Maximize the target window."""
        return self._backend.maximize_window(identifier)

    def restore_window(self, identifier: str | int) -> bool:
        """Restore the target window from minimized or maximized state."""
        return self._backend.restore_window(identifier)

    def move_window(
        self,
        identifier: str | int,
        x: int,
        y: int,
        width: int,
        height: int,
        repaint: bool = True,
    ) -> bool:
        """Resize and reposition target window on the screen."""
        return self._backend.move_window(identifier, x, y, width, height, repaint=repaint)

    def close_window(self, identifier: str | int) -> bool:
        """Gracefully close target window."""
        return self._backend.close_window(identifier)

    # ------------------------------------------------------------------------
    # Input Actions (Mouse and Keyboard)
    # ------------------------------------------------------------------------

    def move_mouse(
        self,
        x: int,
        y: int,
        smooth: bool = True,
        steps: int = 10,
        delay: float = 0.002,
    ) -> tuple[int, int]:
        """Move cursor to target screen coordinate with safety boundary enforcement."""
        target_x, target_y = self._enforce_safety_bounds(x, y)
        self._cursor_pos = self._backend.move_mouse(target_x, target_y, smooth=smooth, steps=steps, delay=delay)
        return self._cursor_pos

    def mouse_down(self, button: str = "left") -> None:
        """Press and hold mouse button at current position."""
        self._enforce_safety_bounds(*self._cursor_pos)
        self._backend.mouse_down(button)

    def mouse_up(self, button: str = "left") -> None:
        """Release mouse button at current position."""
        self._enforce_safety_bounds(*self._cursor_pos)
        self._backend.mouse_up(button)

    def click_mouse(
        self,
        button: str = "left",
        clicks: int = 1,
        interval: float = 0.05,
    ) -> None:
        """Click mouse button at current position one or more times."""
        self._enforce_safety_bounds(*self._cursor_pos)
        self._backend.click_mouse(button=button, clicks=clicks, interval=interval)

    def double_click(self, button: str = "left") -> None:
        """Double-click mouse button at current position."""
        self.click_mouse(button=button, clicks=2, interval=0.05)

    def mouse_drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: str = "left",
        steps: int = 10,
        delay: float = 0.002,
    ) -> None:
        """Drag mouse from start to end coordinates while holding down button."""
        s_x, s_y = self._enforce_safety_bounds(start_x, start_y)
        e_x, e_y = self._enforce_safety_bounds(end_x, end_y)
        self._backend.mouse_drag(s_x, s_y, e_x, e_y, button=button, steps=steps, delay=delay)
        self._cursor_pos = (e_x, e_y)

    def mouse_scroll(self, clicks: int = 1, direction: str = "down") -> None:
        """Scroll mouse wheel vertically."""
        self._enforce_safety_bounds(*self._cursor_pos)
        self._backend.mouse_scroll(clicks=clicks, direction=direction)

    def type_text(self, text: str, delay: float = 0.0) -> None:
        """Type a text string."""
        self._backend.type_text(text, delay=delay)

    def key_down(self, key: str) -> None:
        """Press and hold a keyboard key."""
        self._hotkey_filter.validate(key)
        self._backend.key_down(key)

    def key_up(self, key: str) -> None:
        """Release a keyboard key."""
        self._backend.key_up(key)

    def press_key(self, key: str, delay: float = 0.02) -> None:
        """Press and release a keyboard key."""
        self._hotkey_filter.validate(key)
        self._backend.press_key(key, delay=delay)

    def send_hotkey(self, keys: list[str]) -> None:
        """Execute hotkey combination in order and release in reverse order after safety check."""
        if not keys:
            return
        self._hotkey_filter.validate(keys)
        self._backend.send_hotkey(keys)


# Global controller instance for @skill registrations
_controller = DesktopController()


# ============================================================================
# Registered Effero Skills
# ============================================================================


@skill(
    name="computer_use.desktop.list_windows",
    description="Enumerate visible desktop application windows with titles, dimensions, and process IDs.",
    safety_class=SafetyClass.READ_ONLY,
)
async def list_windows() -> dict[str, Any]:
    """List visible desktop application windows."""
    wins = _controller.list_windows()
    return {
        "status": "success",
        "count": len(wins),
        "windows": [w.to_dict() for w in wins],
    }


@skill(
    name="computer_use.desktop.get_active_window",
    description="Retrieve the active foreground desktop window.",
    safety_class=SafetyClass.READ_ONLY,
)
async def get_active_window() -> dict[str, Any]:
    """Get metadata for the currently active foreground window."""
    win = _controller.get_active_window()
    return {
        "status": "success",
        "window": win.to_dict() if win else None,
    }


@skill(
    name="computer_use.desktop.focus_window",
    description="Activate and focus an application window by handle or title query.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def focus_window(identifier: str | int) -> dict[str, Any]:
    """Focus target window by HWND or title substring."""
    success = _controller.focus_window(identifier)
    return {
        "status": "success" if success else "error",
        "focused": success,
        "identifier": identifier,
    }


@skill(
    name="computer_use.desktop.move_mouse",
    description="Move cursor to screen coordinates (x, y) with safety bounds validation.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def move_mouse(x: int, y: int, smooth: bool = True) -> dict[str, Any]:
    """Move cursor to target coordinates."""
    pos = _controller.move_mouse(x, y, smooth=smooth)
    return {
        "status": "success",
        "cursor": {"x": pos[0], "y": pos[1]},
    }


@skill(
    name="computer_use.desktop.click_mouse",
    description="Click a mouse button at the current cursor position.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def click_mouse(button: str = "left", clicks: int = 1) -> dict[str, Any]:
    """Click mouse button."""
    _controller.click_mouse(button=button, clicks=clicks)
    pos = _controller.get_cursor_position()
    return {
        "status": "success",
        "button": button,
        "clicks": clicks,
        "cursor": {"x": pos[0], "y": pos[1]},
    }


@skill(
    name="computer_use.desktop.mouse_drag",
    description="Drag mouse from start coordinates to end coordinates.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def mouse_drag(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    button: str = "left",
) -> dict[str, Any]:
    """Execute a mouse drag gesture."""
    _controller.mouse_drag(start_x, start_y, end_x, end_y, button=button)
    return {
        "status": "success",
        "from": {"x": start_x, "y": start_y},
        "to": {"x": end_x, "y": end_y},
        "button": button,
    }


@skill(
    name="computer_use.desktop.mouse_scroll",
    description="Scroll the mouse wheel up or down.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def mouse_scroll(clicks: int = 1, direction: str = "down") -> dict[str, Any]:
    """Scroll mouse wheel."""
    _controller.mouse_scroll(clicks=clicks, direction=direction)
    return {
        "status": "success",
        "clicks": clicks,
        "direction": direction,
    }


@skill(
    name="computer_use.desktop.type_text",
    description="Type text string via low-level native keyboard unicode dispatch.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def desktop_type_text(text: str) -> dict[str, Any]:
    """Type arbitrary text characters."""
    _controller.type_text(text)
    return {
        "status": "success",
        "characters_typed": len(text),
    }


@skill(
    name="computer_use.desktop.send_hotkey",
    description="Send hotkey combination with destructive combination prevention.",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def send_hotkey(keys: list[str]) -> dict[str, Any]:
    """Dispatch keyboard hotkey sequence."""
    _controller.send_hotkey(keys)
    return {
        "status": "success",
        "keys": keys,
    }


@skill(
    name="computer_use.desktop.get_cursor_position",
    description="Get current absolute screen coordinates of mouse cursor.",
    safety_class=SafetyClass.READ_ONLY,
)
async def get_cursor_position() -> dict[str, Any]:
    """Query current cursor position."""
    pos = _controller.get_cursor_position()
    return {
        "status": "success",
        "cursor": {"x": pos[0], "y": pos[1]},
    }


@skill(
    name="computer_use.desktop.get_screen_size",
    description="Query primary screen width and height in pixels.",
    safety_class=SafetyClass.READ_ONLY,
)
async def get_screen_size() -> dict[str, Any]:
    """Query screen dimensions."""
    width, height = _controller.get_screen_size()
    return {
        "status": "success",
        "width": width,
        "height": height,
    }


@skill(
    name="computer_use.desktop.set_safety_bounds",
    description="Configure cursor safety bounding box and enforcement policy ('raise' or 'clamp').",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def set_safety_bounds(
    min_x: int,
    min_y: int,
    max_x: int,
    max_y: int,
    policy: str = "raise",
) -> dict[str, Any]:
    """Set active safety bounds."""
    bounds = SafetyBoundingBox(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)
    _controller.set_safety_bounds(bounds, policy=policy)
    return {
        "status": "success",
        "bounds": {
            "min_x": min_x,
            "min_y": min_y,
            "max_x": max_x,
            "max_y": max_y,
            "policy": policy,
        },
    }
