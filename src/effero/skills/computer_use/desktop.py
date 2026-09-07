"""Native Desktop OS automation skill module using Windows user32/kernel32 Win32 APIs."""

from __future__ import annotations

import ctypes
import logging
import re
import sys
import time
from collections.abc import Sequence
from ctypes import wintypes
from dataclasses import asdict, dataclass
from typing import Any

from effero.sdk.skill import SafetyClass, skill

logger = logging.getLogger(__name__)

# ============================================================================
# Win32 Structures and Type Definitions
# ============================================================================

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
else:  # pragma: no cover
    user32 = None  # type: ignore[assignment]
    kernel32 = None  # type: ignore[assignment]


class RECT(ctypes.Structure):
    """Win32 RECT structure defining a rectangle by coordinates."""

    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    """Win32 POINT structure defining (x, y) coordinates."""

    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class MOUSEINPUT(ctypes.Structure):
    """Win32 MOUSEINPUT structure for SendInput."""

    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    """Win32 KEYBDINPUT structure for SendInput."""

    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    """Win32 HARDWAREINPUT structure for SendInput."""

    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    """Win32 union containing mouse, keyboard, or hardware input data."""

    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    """Win32 INPUT structure passed to SendInput."""

    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUT_UNION),
    ]


# Function pointer type for EnumWindows callback
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# ============================================================================
# Win32 Constants
# ============================================================================

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
WHEEL_DELTA = 120

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

SW_HIDE = 0
SW_NORMAL = 1
SW_SHOWMINIMIZED = 2
SW_MAXIMIZE = 3
SW_SHOWNOACTIVATE = 4
SW_SHOW = 5
SW_MINIMIZE = 6
SW_SHOWMINNOACTIVE = 7
SW_SHOWNA = 8
SW_RESTORE = 9

WM_CLOSE = 0x0010

# Virtual Key Codes
VK_MAP: dict[str, int] = {
    "shift": 0x10,
    "lshift": 0xA0,
    "rshift": 0xA1,
    "ctrl": 0x11,
    "control": 0x11,
    "lctrl": 0xA2,
    "rctrl": 0xA3,
    "alt": 0x12,
    "menu": 0x12,
    "lalt": 0xA4,
    "ralt": 0xA5,
    "win": 0x5B,
    "windows": 0x5B,
    "lwin": 0x5B,
    "rwin": 0x5C,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "escape": 0x1B,
    "esc": 0x1B,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "capslock": 0x14,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "printscreen": 0x2C,
    "pause": 0x13,
}

# Add F1 to F24
for _i in range(1, 25):
    VK_MAP[f"f{_i}"] = 0x6F + _i

# Add 0-9
for _i in range(10):
    VK_MAP[str(_i)] = 0x30 + _i

# Add a-z
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK_MAP[_c] = 0x41 + (ord(_c) - ord("a"))


# Configure Win32 function signatures if on Windows
if IS_WINDOWS and user32 is not None:
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.MoveWindow.argtypes = [
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.BOOL,
    ]
    user32.MoveWindow.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
    user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
    user32.ScreenToClient.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.SetCursorPos.restype = wintypes.BOOL
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL


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
# Data Models
# ============================================================================


@dataclass(frozen=True)
class WindowInfo:
    """Represents metadata and geometry of an OS window."""

    hwnd: int
    title: str
    x: int
    y: int
    width: int
    height: int
    is_active: bool
    process_id: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    def from_window(cls, hwnd: int) -> SafetyBoundingBox:
        """Derive bounding box from a live window handle."""
        if not IS_WINDOWS or user32 is None:
            raise RuntimeError("Platform does not support Win32 window bounds.")
        rect = RECT()
        res = user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if not res:
            raise RuntimeError(f"Failed to query GetWindowRect for HWND {hwnd}")
        return cls(min_x=rect.left, min_y=rect.top, max_x=rect.right, max_y=rect.bottom)

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
    """Manages native desktop OS automation, coordinate conversion, and low-level Win32 input."""

    def __init__(
        self,
        safety_bounds: SafetyBoundingBox | None = None,
        safety_policy: str = "raise",
        hotkey_filter: DestructiveHotkeyFilter | None = None,
    ) -> None:
        if not IS_WINDOWS:
            logger.warning("DesktopController initialized on non-Windows platform.")

        self._safety_bounds: SafetyBoundingBox | None = safety_bounds
        self._safety_policy: str = safety_policy.lower()  # "raise" or "clamp"
        self._hotkey_filter: DestructiveHotkeyFilter = hotkey_filter or DestructiveHotkeyFilter()

        # Track internal cursor position
        screen_w, screen_h = self.get_screen_size()
        self._cursor_pos: tuple[int, int] = (screen_w // 2, screen_h // 2)
        if IS_WINDOWS and user32 is not None:
            pt = POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                self._cursor_pos = (pt.x, pt.y)

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
        box = SafetyBoundingBox.from_window(hwnd)
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
        if not IS_WINDOWS or user32 is None:
            return 1920, 1080
        width = int(user32.GetSystemMetrics(SM_CXSCREEN))
        height = int(user32.GetSystemMetrics(SM_CYSCREEN))
        return max(1, width), max(1, height)

    def get_cursor_position(self) -> tuple[int, int]:
        """Query current cursor position (x, y)."""
        if IS_WINDOWS and user32 is not None:
            pt = POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                self._cursor_pos = (pt.x, pt.y)
        return self._cursor_pos

    def set_cursor_position(self, x: int, y: int) -> tuple[int, int]:
        """Directly position the cursor to (x, y) after safety check."""
        target_x, target_y = self._enforce_safety_bounds(x, y)
        if IS_WINDOWS and user32 is not None:
            user32.SetCursorPos(target_x, target_y)
        self._cursor_pos = (target_x, target_y)
        return self._cursor_pos

    def client_to_screen(self, hwnd: int, client_x: int, client_y: int) -> tuple[int, int]:
        """Convert client-area relative coordinates to absolute screen pixels."""
        if not IS_WINDOWS or user32 is None:
            return client_x, client_y
        pt = POINT(x=client_x, y=client_y)
        if user32.ClientToScreen(hwnd, ctypes.byref(pt)):
            return pt.x, pt.y
        # Fallback using window rect
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return rect.left + client_x, rect.top + client_y

    def screen_to_client(self, hwnd: int, screen_x: int, screen_y: int) -> tuple[int, int]:
        """Convert absolute screen pixel coordinates to client-area coordinates."""
        if not IS_WINDOWS or user32 is None:
            return screen_x, screen_y
        pt = POINT(x=screen_x, y=screen_y)
        if user32.ScreenToClient(hwnd, ctypes.byref(pt)):
            return pt.x, pt.y
        # Fallback using window rect
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return screen_x - rect.left, screen_y - rect.top

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
        if not IS_WINDOWS or user32 is None:
            return rel_x, rel_y
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError(f"Could not retrieve window rect for HWND {hwnd}")
        return rect.left + rel_x, rect.top + rel_y

    def screen_to_window_relative(self, hwnd: int, screen_x: int, screen_y: int) -> tuple[int, int]:
        """Convert absolute screen coordinates to window-relative coordinates."""
        if not IS_WINDOWS or user32 is None:
            return screen_x, screen_y
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError(f"Could not retrieve window rect for HWND {hwnd}")
        return screen_x - rect.left, screen_y - rect.top

    # ------------------------------------------------------------------------
    # Window Management and Enumeration
    # ------------------------------------------------------------------------

    def list_windows(self, visible_only: bool = True) -> list[WindowInfo]:
        """Enumerate top-level OS windows and extract their geometry and metadata."""
        if not IS_WINDOWS or user32 is None:
            return []

        active_hwnd = user32.GetForegroundWindow()
        windows: list[WindowInfo] = []

        def enum_callback(hwnd: int, lparam: int) -> bool:
            if visible_only and not user32.IsWindowVisible(hwnd):
                return True

            length = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value

            rect = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top

            # Omit 0x0 or off-screen invisible artifacts if visible_only
            if visible_only and (width <= 0 or height <= 0):
                return True

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            windows.append(
                WindowInfo(
                    hwnd=hwnd,
                    title=title,
                    x=rect.left,
                    y=rect.top,
                    width=width,
                    height=height,
                    is_active=(hwnd == active_hwnd),
                    process_id=pid.value,
                )
            )
            return True

        cb = WNDENUMPROC(enum_callback)
        user32.EnumWindows(cb, 0)
        return windows

    def get_active_window(self) -> WindowInfo | None:
        """Retrieve metadata for the currently active foreground window."""
        if not IS_WINDOWS or user32 is None:
            return None
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        return self.get_window_by_hwnd(hwnd)

    def get_window_by_hwnd(self, hwnd: int) -> WindowInfo | None:
        """Query window metadata by its handle."""
        if not IS_WINDOWS or user32 is None:
            return None
        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value

        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        active_hwnd = user32.GetForegroundWindow()

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        return WindowInfo(
            hwnd=hwnd,
            title=title,
            x=rect.left,
            y=rect.top,
            width=rect.right - rect.left,
            height=rect.bottom - rect.top,
            is_active=(hwnd == active_hwnd),
            process_id=pid.value,
        )

    def get_window_by_title(self, title_query: str) -> WindowInfo | None:
        """Find the first window matching title substring (case-insensitive)."""
        query = title_query.lower()
        windows = self.list_windows(visible_only=False)
        for w in windows:
            if query in w.title.lower():
                return w
        return None

    def _resolve_hwnd(self, identifier: str | int) -> int | None:
        """Resolve HWND from integer handle or title query."""
        if isinstance(identifier, int):
            return identifier
        win = self.get_window_by_title(identifier)
        return win.hwnd if win else None

    def focus_window(self, identifier: str | int) -> bool:
        """Bring window to foreground and give it focus."""
        if not IS_WINDOWS or user32 is None:
            return False
        hwnd = self._resolve_hwnd(identifier)
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, SW_RESTORE)
        ret = bool(user32.SetForegroundWindow(hwnd))
        return ret or True  # SetForegroundWindow returns false if already foreground or blocked by UIPI

    def minimize_window(self, identifier: str | int) -> bool:
        """Minimize the target window."""
        if not IS_WINDOWS or user32 is None:
            return False
        hwnd = self._resolve_hwnd(identifier)
        if not hwnd:
            return False
        return bool(user32.ShowWindow(hwnd, SW_MINIMIZE))

    def maximize_window(self, identifier: str | int) -> bool:
        """Maximize the target window."""
        if not IS_WINDOWS or user32 is None:
            return False
        hwnd = self._resolve_hwnd(identifier)
        if not hwnd:
            return False
        return bool(user32.ShowWindow(hwnd, SW_MAXIMIZE))

    def restore_window(self, identifier: str | int) -> bool:
        """Restore the target window from minimized or maximized state."""
        if not IS_WINDOWS or user32 is None:
            return False
        hwnd = self._resolve_hwnd(identifier)
        if not hwnd:
            return False
        return bool(user32.ShowWindow(hwnd, SW_RESTORE))

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
        if not IS_WINDOWS or user32 is None:
            return False
        hwnd = self._resolve_hwnd(identifier)
        if not hwnd:
            return False
        return bool(user32.MoveWindow(hwnd, x, y, width, height, repaint))

    def close_window(self, identifier: str | int) -> bool:
        """Gracefully close target window via WM_CLOSE."""
        if not IS_WINDOWS or user32 is None:
            return False
        hwnd = self._resolve_hwnd(identifier)
        if not hwnd:
            return False
        return bool(user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))

    # ------------------------------------------------------------------------
    # Low-Level Input Dispatch (SendInput)
    # ------------------------------------------------------------------------

    def _send_inputs(self, inputs: list[INPUT]) -> int:
        """Internal helper to dispatch native Win32 INPUT structures."""
        if not inputs or not IS_WINDOWS or user32 is None:
            return 0
        arr = (INPUT * len(inputs))(*inputs)
        ret = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
        if ret == 0:
            err = ctypes.GetLastError()
            if err != 0 and err != 5:  # Error 5 is access denied in non-interactive/Session 0
                logger.debug("SendInput returned 0 (Win32 error %d)", err)
        return int(ret)

    def _build_mouse_input(
        self,
        dx: int = 0,
        dy: int = 0,
        mouse_data: int = 0,
        flags: int = 0,
    ) -> INPUT:
        """Construct a Win32 INPUT structure for mouse action."""
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.u.mi.dx = dx
        inp.u.mi.dy = dy
        inp.u.mi.mouseData = mouse_data
        inp.u.mi.dwFlags = flags
        inp.u.mi.time = 0
        inp.u.mi.dwExtraInfo = 0
        return inp

    def _build_keyboard_input(
        self,
        vk: int = 0,
        scan: int = 0,
        flags: int = 0,
    ) -> INPUT:
        """Construct a Win32 INPUT structure for keyboard action."""
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.u.ki.wVk = vk
        inp.u.ki.wScan = scan
        inp.u.ki.dwFlags = flags
        inp.u.ki.time = 0
        inp.u.ki.dwExtraInfo = 0
        return inp

    def _dispatch_mouse_move(self, x: int, y: int) -> None:
        """Dispatch native absolute mouse movement to (x, y)."""
        width, height = self.get_screen_size()
        # Normalized absolute coordinates for SendInput [0, 65535]
        norm_x = int(round(x * 65535 / max(1, width - 1)))
        norm_y = int(round(y * 65535 / max(1, height - 1)))

        inp = self._build_mouse_input(
            dx=norm_x,
            dy=norm_y,
            flags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
        )
        if IS_WINDOWS and user32 is not None:
            user32.SetCursorPos(x, y)
        self._send_inputs([inp])

    def move_mouse(
        self,
        x: int,
        y: int,
        smooth: bool = True,
        steps: int = 10,
        delay: float = 0.002,
    ) -> tuple[int, int]:
        """Move cursor to target screen coordinate, with safety enforcement and smooth interpolation."""
        target_x, target_y = self._enforce_safety_bounds(x, y)
        start_x, start_y = self._cursor_pos

        if smooth and steps > 1:
            for i in range(1, steps):
                interp_x = int(start_x + (target_x - start_x) * (i / steps))
                interp_y = int(start_y + (target_y - start_y) * (i / steps))
                self._dispatch_mouse_move(interp_x, interp_y)
                if delay > 0:
                    time.sleep(delay)

        self._dispatch_mouse_move(target_x, target_y)
        self._cursor_pos = (target_x, target_y)
        return self._cursor_pos

    def mouse_down(self, button: str = "left") -> None:
        """Press and hold mouse button at current position."""
        self._enforce_safety_bounds(*self._cursor_pos)
        b_lower = button.lower()
        flag = MOUSEEVENTF_LEFTDOWN
        if b_lower == "right":
            flag = MOUSEEVENTF_RIGHTDOWN
        elif b_lower == "middle":
            flag = MOUSEEVENTF_MIDDLEDOWN

        inp = self._build_mouse_input(flags=flag)
        self._send_inputs([inp])

    def mouse_up(self, button: str = "left") -> None:
        """Release mouse button at current position."""
        self._enforce_safety_bounds(*self._cursor_pos)
        b_lower = button.lower()
        flag = MOUSEEVENTF_LEFTUP
        if b_lower == "right":
            flag = MOUSEEVENTF_RIGHTUP
        elif b_lower == "middle":
            flag = MOUSEEVENTF_MIDDLEUP

        inp = self._build_mouse_input(flags=flag)
        self._send_inputs([inp])

    def click_mouse(
        self,
        button: str = "left",
        clicks: int = 1,
        interval: float = 0.05,
    ) -> None:
        """Click mouse button at current position one or more times."""
        self._enforce_safety_bounds(*self._cursor_pos)
        for i in range(clicks):
            self.mouse_down(button)
            time.sleep(interval)
            self.mouse_up(button)
            if i < clicks - 1 and interval > 0:
                time.sleep(interval)

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
    ) -> None:
        """Drag mouse from start to end coordinates while holding down button."""
        # Enforce safety bounds on both endpoints
        s_x, s_y = self._enforce_safety_bounds(start_x, start_y)
        e_x, e_y = self._enforce_safety_bounds(end_x, end_y)

        self.move_mouse(s_x, s_y, smooth=False)
        self.mouse_down(button)
        self.move_mouse(e_x, e_y, smooth=True, steps=steps)
        self.mouse_up(button)

    def mouse_scroll(self, clicks: int = 1, direction: str = "down") -> None:
        """Scroll mouse wheel vertically."""
        self._enforce_safety_bounds(*self._cursor_pos)
        d_lower = direction.lower()
        delta = -clicks * WHEEL_DELTA if d_lower in ("down", "d") else clicks * WHEEL_DELTA

        inp = self._build_mouse_input(mouse_data=delta, flags=MOUSEEVENTF_WHEEL)
        self._send_inputs([inp])

    # ------------------------------------------------------------------------
    # Keyboard Actions and Hotkey Dispatch
    # ------------------------------------------------------------------------

    def _resolve_vk(self, key_name: str) -> int:
        """Resolve virtual key code from key name or character."""
        canonical = DestructiveHotkeyFilter.normalize_key(key_name)
        if canonical in VK_MAP:
            return VK_MAP[canonical]

        if len(key_name) == 1 and IS_WINDOWS and user32 is not None:
            vk_val = user32.VkKeyScanW(ord(key_name))
            if vk_val != -1:
                return vk_val & 0xFF

        raise ValueError(f"Unsupported virtual key '{key_name}'")

    def type_text(self, text: str, delay: float = 0.0) -> None:
        """Type a unicode string using Win32 KEYEVENTF_UNICODE."""
        if not text:
            return

        inputs: list[INPUT] = []
        for char in text:
            code = ord(char)
            # Key down
            down = self._build_keyboard_input(scan=code, flags=KEYEVENTF_UNICODE)
            # Key up
            up = self._build_keyboard_input(scan=code, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
            inputs.extend([down, up])

        if delay <= 0:
            self._send_inputs(inputs)
        else:
            for i in range(0, len(inputs), 2):
                self._send_inputs(inputs[i : i + 2])
                time.sleep(delay)

    def key_down(self, key: str) -> None:
        """Press and hold a keyboard key."""
        self._hotkey_filter.validate(key)
        vk = self._resolve_vk(key)
        inp = self._build_keyboard_input(vk=vk)
        self._send_inputs([inp])

    def key_up(self, key: str) -> None:
        """Release a keyboard key."""
        vk = self._resolve_vk(key)
        inp = self._build_keyboard_input(vk=vk, flags=KEYEVENTF_KEYUP)
        self._send_inputs([inp])

    def press_key(self, key: str, delay: float = 0.02) -> None:
        """Press and release a keyboard key."""
        self.key_down(key)
        if delay > 0:
            time.sleep(delay)
        self.key_up(key)

    def send_hotkey(self, keys: list[str]) -> None:
        """Execute hotkey combination in order and release in reverse order after safety check."""
        if not keys:
            return

        # Validate against destructive hotkey filter
        self._hotkey_filter.validate(keys)

        # Resolve all VK codes first
        vks = [self._resolve_vk(k) for k in keys]

        # Press modifiers / keys in forward order
        for vk in vks:
            inp = self._build_keyboard_input(vk=vk)
            self._send_inputs([inp])
            time.sleep(0.01)

        time.sleep(0.02)

        # Release keys in reverse order
        for vk in reversed(vks):
            inp = self._build_keyboard_input(vk=vk, flags=KEYEVENTF_KEYUP)
            self._send_inputs([inp])
            time.sleep(0.01)


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
