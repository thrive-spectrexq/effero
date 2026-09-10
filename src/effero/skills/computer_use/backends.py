"""Cross-platform Desktop OS automation backends.

Provides abstract DesktopBackend with concrete implementations:
- Win32DesktopBackend: Native Windows user32/kernel32 SendInput and window management
- LinuxDesktopBackend: Linux X11 automation using xdotool and wmctrl (with virtual fallback)
- HeadlessDesktopBackend: In-memory virtual desktop for testing and headless/container environments
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from ctypes import wintypes
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
else:  # pragma: no cover
    user32 = None  # type: ignore[assignment]
    kernel32 = None  # type: ignore[assignment]


# ============================================================================
# Win32 Structures and Type Definitions
# ============================================================================


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


if IS_WINDOWS:
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)  # type: ignore[attr-defined]
else:  # pragma: no cover
    WNDENUMPROC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)  # type: ignore[assignment]

# Win32 Constants
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

for _i in range(1, 25):
    VK_MAP[f"f{_i}"] = 0x6F + _i

for _i in range(10):
    VK_MAP[str(_i)] = 0x30 + _i

for _c in "abcdefghijklmnopqrstuvwxyz":
    VK_MAP[_c] = 0x41 + (ord(_c) - ord("a"))

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


def validate_virtual_key(key_name: str) -> str:
    """Validate a key string against canonical desktop keys, raising ValueError if unsupported."""
    canonical = key_name.strip().lower()
    canonical = KEY_ALIASES.get(canonical, canonical)
    if canonical in VK_MAP or len(key_name) == 1:
        return canonical
    raise ValueError(f"Unsupported virtual key '{key_name}'")


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


# ============================================================================
# Abstract Desktop Backend
# ============================================================================


class DesktopBackend(ABC):
    """Abstract base class for OS desktop automation backends."""

    @abstractmethod
    def get_screen_size(self) -> tuple[int, int]:
        """Query screen dimensions (width, height) in pixels."""
        ...

    @abstractmethod
    def get_cursor_position(self) -> tuple[int, int]:
        """Query current cursor position (x, y)."""
        ...

    @abstractmethod
    def set_cursor_position(self, x: int, y: int) -> tuple[int, int]:
        """Position cursor directly to (x, y)."""
        ...

    @abstractmethod
    def move_mouse(
        self,
        x: int,
        y: int,
        smooth: bool = True,
        steps: int = 10,
        delay: float = 0.002,
    ) -> tuple[int, int]:
        """Move mouse cursor with optional smooth interpolation."""
        ...

    @abstractmethod
    def click_mouse(self, button: str = "left", clicks: int = 1, interval: float = 0.05) -> None:
        """Click mouse button."""
        ...

    @abstractmethod
    def mouse_down(self, button: str = "left") -> None:
        """Press and hold mouse button."""
        ...

    @abstractmethod
    def mouse_up(self, button: str = "left") -> None:
        """Release mouse button."""
        ...

    @abstractmethod
    def double_click(self, button: str = "left") -> None:
        """Double click mouse button."""
        ...

    @abstractmethod
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
        """Drag mouse between two points."""
        ...

    @abstractmethod
    def mouse_scroll(self, clicks: int = 1, direction: str = "down") -> None:
        """Scroll mouse wheel."""
        ...

    @abstractmethod
    def type_text(self, text: str, delay: float = 0.0) -> None:
        """Type text string."""
        ...

    @abstractmethod
    def press_key(self, key: str, delay: float = 0.02) -> None:
        """Press and release a keyboard key."""
        ...

    @abstractmethod
    def key_down(self, key: str) -> None:
        """Press and hold a keyboard key."""
        ...

    @abstractmethod
    def key_up(self, key: str) -> None:
        """Release a keyboard key."""
        ...

    @abstractmethod
    def send_hotkey(self, keys: Sequence[str]) -> None:
        """Dispatch hotkey combination."""
        ...

    @abstractmethod
    def list_windows(self, visible_only: bool = True) -> list[WindowInfo]:
        """List top-level windows."""
        ...

    @abstractmethod
    def get_active_window(self) -> WindowInfo | None:
        """Retrieve foreground active window."""
        ...

    @abstractmethod
    def get_window_by_hwnd(self, hwnd: int) -> WindowInfo | None:
        """Query window metadata by handle."""
        ...

    @abstractmethod
    def get_window_by_title(self, title_query: str) -> WindowInfo | None:
        """Query window metadata by title substring."""
        ...

    @abstractmethod
    def focus_window(self, identifier: str | int) -> bool:
        """Bring window to foreground."""
        ...

    @abstractmethod
    def minimize_window(self, identifier: str | int) -> bool:
        """Minimize window."""
        ...

    @abstractmethod
    def maximize_window(self, identifier: str | int) -> bool:
        """Maximize window."""
        ...

    @abstractmethod
    def restore_window(self, identifier: str | int) -> bool:
        """Restore window."""
        ...

    @abstractmethod
    def move_window(
        self,
        identifier: str | int,
        x: int,
        y: int,
        width: int,
        height: int,
        repaint: bool = True,
    ) -> bool:
        """Move and resize window."""
        ...

    @abstractmethod
    def close_window(self, identifier: str | int) -> bool:
        """Close window."""
        ...

    @abstractmethod
    def client_to_screen(self, hwnd: int, client_x: int, client_y: int) -> tuple[int, int]:
        """Convert window client coordinates to screen coordinates."""
        ...

    @abstractmethod
    def screen_to_client(self, hwnd: int, screen_x: int, screen_y: int) -> tuple[int, int]:
        """Convert screen coordinates to window client coordinates."""
        ...

    @abstractmethod
    def get_window_rect(self, hwnd: int) -> tuple[int, int, int, int] | None:
        """Get window bounds rectangle (left, top, right, bottom)."""
        ...


# ============================================================================
# Win32 Desktop Backend
# ============================================================================


class Win32DesktopBackend(DesktopBackend):
    """Windows user32/kernel32 native implementation."""

    def __init__(self) -> None:
        if not IS_WINDOWS or user32 is None:
            logger.warning("Win32DesktopBackend instantiated on non-Windows platform.")
        w, h = self.get_screen_size()
        self._cursor_pos = (w // 2, h // 2)
        if IS_WINDOWS and user32 is not None:
            pt = POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                self._cursor_pos = (pt.x, pt.y)

    def get_screen_size(self) -> tuple[int, int]:
        if not IS_WINDOWS or user32 is None:
            return 1920, 1080
        w = int(user32.GetSystemMetrics(SM_CXSCREEN))
        h = int(user32.GetSystemMetrics(SM_CYSCREEN))
        return max(1, w), max(1, h)

    def get_cursor_position(self) -> tuple[int, int]:
        if IS_WINDOWS and user32 is not None:
            pt = POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                self._cursor_pos = (pt.x, pt.y)
        return self._cursor_pos

    def set_cursor_position(self, x: int, y: int) -> tuple[int, int]:
        if IS_WINDOWS and user32 is not None:
            user32.SetCursorPos(x, y)
        self._cursor_pos = (x, y)
        return self._cursor_pos

    def _send_inputs(self, inputs: list[INPUT]) -> int:
        if not inputs or not IS_WINDOWS or user32 is None:
            return 0
        arr = (INPUT * len(inputs))(*inputs)
        ret = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
        return int(ret)

    def _build_mouse_input(self, dx: int = 0, dy: int = 0, mouse_data: int = 0, flags: int = 0) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.u.mi.dx = dx
        inp.u.mi.dy = dy
        inp.u.mi.mouseData = mouse_data
        inp.u.mi.dwFlags = flags
        inp.u.mi.time = 0
        inp.u.mi.dwExtraInfo = 0
        return inp

    def _build_keyboard_input(self, vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.u.ki.wVk = vk
        inp.u.ki.wScan = scan
        inp.u.ki.dwFlags = flags
        inp.u.ki.time = 0
        inp.u.ki.dwExtraInfo = 0
        return inp

    def _dispatch_mouse_move(self, x: int, y: int) -> None:
        width, height = self.get_screen_size()
        norm_x = int(round(x * 65535 / max(1, width - 1)))
        norm_y = int(round(y * 65535 / max(1, height - 1)))
        inp = self._build_mouse_input(dx=norm_x, dy=norm_y, flags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
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
        start_x, start_y = self.get_cursor_position()
        if smooth and steps > 1:
            for i in range(1, steps):
                interp_x = int(start_x + (x - start_x) * (i / steps))
                interp_y = int(start_y + (y - start_y) * (i / steps))
                self._dispatch_mouse_move(interp_x, interp_y)
                if delay > 0:
                    time.sleep(delay)
        self._dispatch_mouse_move(x, y)
        self._cursor_pos = (x, y)
        return self._cursor_pos

    def mouse_down(self, button: str = "left") -> None:
        b = button.lower()
        flag = MOUSEEVENTF_LEFTDOWN
        if b == "right":
            flag = MOUSEEVENTF_RIGHTDOWN
        elif b == "middle":
            flag = MOUSEEVENTF_MIDDLEDOWN
        self._send_inputs([self._build_mouse_input(flags=flag)])

    def mouse_up(self, button: str = "left") -> None:
        b = button.lower()
        flag = MOUSEEVENTF_LEFTUP
        if b == "right":
            flag = MOUSEEVENTF_RIGHTUP
        elif b == "middle":
            flag = MOUSEEVENTF_MIDDLEUP
        self._send_inputs([self._build_mouse_input(flags=flag)])

    def click_mouse(self, button: str = "left", clicks: int = 1, interval: float = 0.05) -> None:
        for i in range(clicks):
            self.mouse_down(button)
            time.sleep(interval)
            self.mouse_up(button)
            if i < clicks - 1 and interval > 0:
                time.sleep(interval)

    def double_click(self, button: str = "left") -> None:
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
        self.move_mouse(start_x, start_y, smooth=False)
        self.mouse_down(button)
        self.move_mouse(end_x, end_y, smooth=True, steps=steps, delay=delay)
        self.mouse_up(button)

    def mouse_scroll(self, clicks: int = 1, direction: str = "down") -> None:
        d_lower = direction.lower()
        delta = -clicks * WHEEL_DELTA if d_lower in ("down", "d") else clicks * WHEEL_DELTA
        self._send_inputs([self._build_mouse_input(mouse_data=delta, flags=MOUSEEVENTF_WHEEL)])

    def _resolve_vk(self, key_name: str) -> int:
        canonical = key_name.strip().lower()
        alias_map = {
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
        canonical = alias_map.get(canonical, canonical)
        if canonical in VK_MAP:
            return VK_MAP[canonical]
        if len(key_name) == 1 and IS_WINDOWS and user32 is not None:
            vk_val = user32.VkKeyScanW(ord(key_name))
            if vk_val != -1:
                return vk_val & 0xFF
        raise ValueError(f"Unsupported virtual key '{key_name}'")

    def type_text(self, text: str, delay: float = 0.0) -> None:
        if not text:
            return
        inputs: list[INPUT] = []
        for char in text:
            code = ord(char)
            down = self._build_keyboard_input(scan=code, flags=KEYEVENTF_UNICODE)
            up = self._build_keyboard_input(scan=code, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
            inputs.extend([down, up])

        if delay <= 0:
            self._send_inputs(inputs)
        else:
            for i in range(0, len(inputs), 2):
                self._send_inputs(inputs[i : i + 2])
                time.sleep(delay)

    def key_down(self, key: str) -> None:
        vk = self._resolve_vk(key)
        self._send_inputs([self._build_keyboard_input(vk=vk)])

    def key_up(self, key: str) -> None:
        vk = self._resolve_vk(key)
        self._send_inputs([self._build_keyboard_input(vk=vk, flags=KEYEVENTF_KEYUP)])

    def press_key(self, key: str, delay: float = 0.02) -> None:
        self.key_down(key)
        if delay > 0:
            time.sleep(delay)
        self.key_up(key)

    def send_hotkey(self, keys: Sequence[str]) -> None:
        if not keys:
            return
        vks = [self._resolve_vk(k) for k in keys]
        for vk in vks:
            self._send_inputs([self._build_keyboard_input(vk=vk)])
            time.sleep(0.01)
        time.sleep(0.02)
        for vk in reversed(vks):
            self._send_inputs([self._build_keyboard_input(vk=vk, flags=KEYEVENTF_KEYUP)])
            time.sleep(0.01)

    def list_windows(self, visible_only: bool = True) -> list[WindowInfo]:
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
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if visible_only and (w <= 0 or h <= 0):
                return True

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            windows.append(
                WindowInfo(
                    hwnd=hwnd,
                    title=title,
                    x=rect.left,
                    y=rect.top,
                    width=w,
                    height=h,
                    is_active=(hwnd == active_hwnd),
                    process_id=pid.value,
                )
            )
            return True

        cb = WNDENUMPROC(enum_callback)
        user32.EnumWindows(cb, 0)
        return windows

    def get_active_window(self) -> WindowInfo | None:
        if not IS_WINDOWS or user32 is None:
            return None
        hwnd = user32.GetForegroundWindow()
        return self.get_window_by_hwnd(hwnd) if hwnd else None

    def get_window_by_hwnd(self, hwnd: int) -> WindowInfo | None:
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
        q = title_query.lower()
        for w in self.list_windows(visible_only=False):
            if q in w.title.lower():
                return w
        return None

    def _resolve_hwnd(self, identifier: str | int) -> int | None:
        if isinstance(identifier, int):
            return identifier
        win = self.get_window_by_title(identifier)
        return win.hwnd if win else None

    def focus_window(self, identifier: str | int) -> bool:
        if not IS_WINDOWS or user32 is None:
            return False
        hwnd = self._resolve_hwnd(identifier)
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True

    def minimize_window(self, identifier: str | int) -> bool:
        if not IS_WINDOWS or user32 is None:
            return False
        hwnd = self._resolve_hwnd(identifier)
        return bool(user32.ShowWindow(hwnd, SW_MINIMIZE)) if hwnd else False

    def maximize_window(self, identifier: str | int) -> bool:
        if not IS_WINDOWS or user32 is None:
            return False
        hwnd = self._resolve_hwnd(identifier)
        return bool(user32.ShowWindow(hwnd, SW_MAXIMIZE)) if hwnd else False

    def restore_window(self, identifier: str | int) -> bool:
        if not IS_WINDOWS or user32 is None:
            return False
        hwnd = self._resolve_hwnd(identifier)
        return bool(user32.ShowWindow(hwnd, SW_RESTORE)) if hwnd else False

    def move_window(
        self,
        identifier: str | int,
        x: int,
        y: int,
        width: int,
        height: int,
        repaint: bool = True,
    ) -> bool:
        if not IS_WINDOWS or user32 is None:
            return False
        hwnd = self._resolve_hwnd(identifier)
        return bool(user32.MoveWindow(hwnd, x, y, width, height, repaint)) if hwnd else False

    def close_window(self, identifier: str | int) -> bool:
        if not IS_WINDOWS or user32 is None:
            return False
        hwnd = self._resolve_hwnd(identifier)
        return bool(user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)) if hwnd else False

    def client_to_screen(self, hwnd: int, client_x: int, client_y: int) -> tuple[int, int]:
        if not IS_WINDOWS or user32 is None:
            return client_x, client_y
        pt = POINT(x=client_x, y=client_y)
        if user32.ClientToScreen(hwnd, ctypes.byref(pt)):
            return pt.x, pt.y
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return rect.left + client_x, rect.top + client_y

    def screen_to_client(self, hwnd: int, screen_x: int, screen_y: int) -> tuple[int, int]:
        if not IS_WINDOWS or user32 is None:
            return screen_x, screen_y
        pt = POINT(x=screen_x, y=screen_y)
        if user32.ScreenToClient(hwnd, ctypes.byref(pt)):
            return pt.x, pt.y
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return screen_x - rect.left, screen_y - rect.top

    def get_window_rect(self, hwnd: int) -> tuple[int, int, int, int] | None:
        if not IS_WINDOWS or user32 is None:
            return None
        rect = RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return rect.left, rect.top, rect.right, rect.bottom
        return None


# ============================================================================
# Headless Virtual Desktop Backend
# ============================================================================


class HeadlessDesktopBackend(DesktopBackend):
    """In-memory virtual desktop backend for testing and headless CI/Docker environments."""

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080) -> None:
        self.width = max(1, screen_width)
        self.height = max(1, screen_height)
        self.cursor_pos: tuple[int, int] = (screen_width // 2, screen_height // 2)
        self.windows: dict[int, WindowInfo] = {}
        self.active_hwnd: int | None = None
        self.typed_text: list[str] = []
        self.pressed_keys: list[str] = []
        self.sent_hotkeys: list[list[str]] = []
        self.clicks: list[dict[str, Any]] = []

    def get_screen_size(self) -> tuple[int, int]:
        return self.width, self.height

    def get_cursor_position(self) -> tuple[int, int]:
        return self.cursor_pos

    def set_cursor_position(self, x: int, y: int) -> tuple[int, int]:
        self.cursor_pos = (x, y)
        return self.cursor_pos

    def move_mouse(
        self,
        x: int,
        y: int,
        smooth: bool = True,
        steps: int = 10,
        delay: float = 0.002,
    ) -> tuple[int, int]:
        self.cursor_pos = (x, y)
        return self.cursor_pos

    def click_mouse(self, button: str = "left", clicks: int = 1, interval: float = 0.05) -> None:
        self.clicks.append({"button": button, "clicks": clicks, "pos": self.cursor_pos})

    def mouse_down(self, button: str = "left") -> None:
        pass

    def mouse_up(self, button: str = "left") -> None:
        pass

    def double_click(self, button: str = "left") -> None:
        self.click_mouse(button=button, clicks=2)

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
        self.cursor_pos = (end_x, end_y)

    def mouse_scroll(self, clicks: int = 1, direction: str = "down") -> None:
        pass

    def type_text(self, text: str, delay: float = 0.0) -> None:
        self.typed_text.append(text)

    def press_key(self, key: str, delay: float = 0.02) -> None:
        validate_virtual_key(key)
        self.pressed_keys.append(key)

    def key_down(self, key: str) -> None:
        validate_virtual_key(key)
        self.pressed_keys.append(key)

    def key_up(self, key: str) -> None:
        validate_virtual_key(key)

    def send_hotkey(self, keys: Sequence[str]) -> None:
        for k in keys:
            validate_virtual_key(k)
        self.sent_hotkeys.append(list(keys))

    def add_virtual_window(
        self,
        hwnd: int,
        title: str,
        x: int = 100,
        y: int = 100,
        width: int = 800,
        height: int = 600,
        is_active: bool = False,
        process_id: int = 1000,
    ) -> WindowInfo:
        win = WindowInfo(
            hwnd=hwnd,
            title=title,
            x=x,
            y=y,
            width=width,
            height=height,
            is_active=is_active,
            process_id=process_id,
        )
        self.windows[hwnd] = win
        if is_active:
            self.active_hwnd = hwnd
        return win

    def list_windows(self, visible_only: bool = True) -> list[WindowInfo]:
        return list(self.windows.values())

    def get_active_window(self) -> WindowInfo | None:
        if self.active_hwnd and self.active_hwnd in self.windows:
            return self.windows[self.active_hwnd]
        if self.windows:
            return next(iter(self.windows.values()))
        return None

    def get_window_by_hwnd(self, hwnd: int) -> WindowInfo | None:
        return self.windows.get(hwnd)

    def get_window_by_title(self, title_query: str) -> WindowInfo | None:
        q = title_query.lower()
        for w in self.windows.values():
            if q in w.title.lower():
                return w
        return None

    def _resolve_hwnd(self, identifier: str | int) -> int | None:
        if isinstance(identifier, int):
            return identifier
        win = self.get_window_by_title(identifier)
        return win.hwnd if win else None

    def focus_window(self, identifier: str | int) -> bool:
        hwnd = self._resolve_hwnd(identifier)
        if hwnd and hwnd in self.windows:
            self.active_hwnd = hwnd
            return True
        return False

    def minimize_window(self, identifier: str | int) -> bool:
        hwnd = self._resolve_hwnd(identifier)
        return bool(hwnd and hwnd in self.windows)

    def maximize_window(self, identifier: str | int) -> bool:
        hwnd = self._resolve_hwnd(identifier)
        return bool(hwnd and hwnd in self.windows)

    def restore_window(self, identifier: str | int) -> bool:
        hwnd = self._resolve_hwnd(identifier)
        return bool(hwnd and hwnd in self.windows)

    def move_window(
        self,
        identifier: str | int,
        x: int,
        y: int,
        width: int,
        height: int,
        repaint: bool = True,
    ) -> bool:
        hwnd = self._resolve_hwnd(identifier)
        if hwnd and hwnd in self.windows:
            cur = self.windows[hwnd]
            self.windows[hwnd] = WindowInfo(
                hwnd=cur.hwnd,
                title=cur.title,
                x=x,
                y=y,
                width=width,
                height=height,
                is_active=cur.is_active,
                process_id=cur.process_id,
            )
            return True
        return False

    def close_window(self, identifier: str | int) -> bool:
        hwnd = self._resolve_hwnd(identifier)
        if hwnd and hwnd in self.windows:
            del self.windows[hwnd]
            if self.active_hwnd == hwnd:
                self.active_hwnd = None
            return True
        return False

    def client_to_screen(self, hwnd: int, client_x: int, client_y: int) -> tuple[int, int]:
        win = self.windows.get(hwnd)
        if win:
            return win.x + client_x, win.y + client_y
        return client_x, client_y

    def screen_to_client(self, hwnd: int, screen_x: int, screen_y: int) -> tuple[int, int]:
        win = self.windows.get(hwnd)
        if win:
            return screen_x - win.x, screen_y - win.y
        return screen_x, screen_y

    def get_window_rect(self, hwnd: int) -> tuple[int, int, int, int] | None:
        win = self.windows.get(hwnd)
        if win:
            return (win.x, win.y, win.x + win.width, win.y + win.height)
        return None


# ============================================================================
# Linux Desktop Backend (xdotool & wmctrl)
# ============================================================================


class LinuxDesktopBackend(DesktopBackend):
    """Linux X11 automation backend using xdotool and wmctrl with graceful fallback."""

    def __init__(self) -> None:
        self._has_display = bool(os.environ.get("DISPLAY"))
        self._has_xdotool = bool(shutil.which("xdotool")) and self._has_display
        self._has_wmctrl = bool(shutil.which("wmctrl")) and self._has_display
        self._virtual = HeadlessDesktopBackend()

    def _run_cmd(self, cmd: list[str]) -> str | None:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0, check=True)
            return res.stdout.strip()
        except Exception as e:
            logger.debug("Linux desktop command '%s' failed: %s", " ".join(cmd), e)
            return None

    def get_screen_size(self) -> tuple[int, int]:
        if self._has_xdotool:
            out = self._run_cmd(["xdotool", "getdisplaygeometry"])
            if out:
                parts = out.split()
                if len(parts) >= 2:
                    try:
                        return int(parts[0]), int(parts[1])
                    except ValueError:
                        pass
        return self._virtual.get_screen_size()

    def get_cursor_position(self) -> tuple[int, int]:
        if self._has_xdotool:
            out = self._run_cmd(["xdotool", "getmouselocation", "--shell"])
            if out:
                x_match = re.search(r"X=(\d+)", out)
                y_match = re.search(r"Y=(\d+)", out)
                if x_match and y_match:
                    pos = (int(x_match.group(1)), int(y_match.group(1)))
                    self._virtual.cursor_pos = pos
                    return pos
        return self._virtual.get_cursor_position()

    def set_cursor_position(self, x: int, y: int) -> tuple[int, int]:
        if self._has_xdotool:
            self._run_cmd(["xdotool", "mousemove", str(x), str(y)])
        return self._virtual.set_cursor_position(x, y)

    def move_mouse(
        self,
        x: int,
        y: int,
        smooth: bool = True,
        steps: int = 10,
        delay: float = 0.002,
    ) -> tuple[int, int]:
        if self._has_xdotool:
            if smooth and steps > 1:
                cur_x, cur_y = self.get_cursor_position()
                for i in range(1, steps):
                    ix = int(cur_x + (x - cur_x) * (i / steps))
                    iy = int(cur_y + (y - cur_y) * (i / steps))
                    self._run_cmd(["xdotool", "mousemove", str(ix), str(iy)])
                    if delay > 0:
                        time.sleep(delay)
            self._run_cmd(["xdotool", "mousemove", str(x), str(y)])
        return self._virtual.move_mouse(x, y, smooth=smooth, steps=steps, delay=delay)

    def _button_code(self, button: str) -> str:
        b = button.lower()
        if b == "right":
            return "3"
        if b == "middle":
            return "2"
        return "1"

    def click_mouse(self, button: str = "left", clicks: int = 1, interval: float = 0.05) -> None:
        if self._has_xdotool:
            btn = self._button_code(button)
            delay_ms = int(interval * 1000)
            self._run_cmd(["xdotool", "click", "--repeat", str(clicks), "--delay", str(delay_ms), btn])
        self._virtual.click_mouse(button=button, clicks=clicks, interval=interval)

    def mouse_down(self, button: str = "left") -> None:
        if self._has_xdotool:
            self._run_cmd(["xdotool", "mousedown", self._button_code(button)])
        self._virtual.mouse_down(button)

    def mouse_up(self, button: str = "left") -> None:
        if self._has_xdotool:
            self._run_cmd(["xdotool", "mouseup", self._button_code(button)])
        self._virtual.mouse_up(button)

    def double_click(self, button: str = "left") -> None:
        self.click_mouse(button=button, clicks=2)

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
        self.move_mouse(start_x, start_y, smooth=False)
        self.mouse_down(button)
        self.move_mouse(end_x, end_y, smooth=True, steps=steps, delay=delay)
        self.mouse_up(button)

    def mouse_scroll(self, clicks: int = 1, direction: str = "down") -> None:
        if self._has_xdotool:
            btn = "4" if direction.lower() in ("up", "u") else "5"
            self._run_cmd(["xdotool", "click", "--repeat", str(clicks), btn])
        self._virtual.mouse_scroll(clicks, direction)

    def type_text(self, text: str, delay: float = 0.0) -> None:
        if self._has_xdotool and text:
            delay_ms = int(delay * 1000)
            self._run_cmd(["xdotool", "type", "--delay", str(delay_ms), "--", text])
        self._virtual.type_text(text, delay=delay)

    def press_key(self, key: str, delay: float = 0.02) -> None:
        validate_virtual_key(key)
        if self._has_xdotool:
            self._run_cmd(["xdotool", "key", key])
        self._virtual.press_key(key, delay=delay)

    def key_down(self, key: str) -> None:
        validate_virtual_key(key)
        if self._has_xdotool:
            self._run_cmd(["xdotool", "keydown", key])
        self._virtual.key_down(key)

    def key_up(self, key: str) -> None:
        validate_virtual_key(key)
        if self._has_xdotool:
            self._run_cmd(["xdotool", "keyup", key])
        self._virtual.key_up(key)

    def send_hotkey(self, keys: Sequence[str]) -> None:
        for k in keys:
            validate_virtual_key(k)
        if self._has_xdotool and keys:
            combo = "+".join(keys)
            self._run_cmd(["xdotool", "key", combo])
        self._virtual.send_hotkey(keys)

    def list_windows(self, visible_only: bool = True) -> list[WindowInfo]:
        if self._has_wmctrl:
            out = self._run_cmd(["wmctrl", "-l", "-G", "-p"])
            if out:
                active_out = self._run_cmd(["xdotool", "getactivewindow"]) if self._has_xdotool else None
                active_id = int(active_out) if active_out and active_out.isdigit() else None
                windows = []
                for line in out.splitlines():
                    parts = line.split(maxsplit=8)
                    if len(parts) >= 9:
                        try:
                            hwnd_val = int(parts[0], 16)
                            pid_val = int(parts[2])
                            x_val = int(parts[3])
                            y_val = int(parts[4])
                            w_val = int(parts[5])
                            h_val = int(parts[6])
                            title_val = parts[8]
                            if visible_only and (w_val <= 0 or h_val <= 0):
                                continue
                            windows.append(
                                WindowInfo(
                                    hwnd=hwnd_val,
                                    title=title_val,
                                    x=x_val,
                                    y=y_val,
                                    width=w_val,
                                    height=h_val,
                                    is_active=(hwnd_val == active_id),
                                    process_id=pid_val,
                                )
                            )
                        except (ValueError, IndexError):
                            continue
                if windows:
                    return windows
        return self._virtual.list_windows(visible_only=visible_only)

    def get_active_window(self) -> WindowInfo | None:
        if self._has_xdotool:
            out = self._run_cmd(["xdotool", "getactivewindow"])
            if out and out.isdigit():
                return self.get_window_by_hwnd(int(out))
        return self._virtual.get_active_window()

    def get_window_by_hwnd(self, hwnd: int) -> WindowInfo | None:
        for w in self.list_windows(visible_only=False):
            if w.hwnd == hwnd:
                return w
        return self._virtual.get_window_by_hwnd(hwnd)

    def get_window_by_title(self, title_query: str) -> WindowInfo | None:
        q = title_query.lower()
        for w in self.list_windows(visible_only=False):
            if q in w.title.lower():
                return w
        return self._virtual.get_window_by_title(title_query)

    def focus_window(self, identifier: str | int) -> bool:
        if self._has_wmctrl:
            cmd = ["wmctrl", "-i", "-a", hex(identifier) if isinstance(identifier, int) else str(identifier)]
            if self._run_cmd(cmd) is not None:
                return True
        return self._virtual.focus_window(identifier)

    def minimize_window(self, identifier: str | int) -> bool:
        if self._has_wmctrl:
            target = hex(identifier) if isinstance(identifier, int) else str(identifier)
            if self._run_cmd(["wmctrl", "-i", "-r", target, "-b", "add,hidden"]) is not None:
                return True
        return self._virtual.minimize_window(identifier)

    def maximize_window(self, identifier: str | int) -> bool:
        if self._has_wmctrl:
            target = hex(identifier) if isinstance(identifier, int) else str(identifier)
            if self._run_cmd(["wmctrl", "-i", "-r", target, "-b", "add,maximized_vert,maximized_horz"]) is not None:
                return True
        return self._virtual.maximize_window(identifier)

    def restore_window(self, identifier: str | int) -> bool:
        if self._has_wmctrl:
            target = hex(identifier) if isinstance(identifier, int) else str(identifier)
            if self._run_cmd(["wmctrl", "-i", "-r", target, "-b", "remove,maximized_vert,maximized_horz"]) is not None:
                return True
        return self._virtual.restore_window(identifier)

    def move_window(
        self,
        identifier: str | int,
        x: int,
        y: int,
        width: int,
        height: int,
        repaint: bool = True,
    ) -> bool:
        if self._has_wmctrl:
            target = hex(identifier) if isinstance(identifier, int) else str(identifier)
            geo = f"0,{x},{y},{width},{height}"
            if self._run_cmd(["wmctrl", "-i", "-r", target, "-e", geo]) is not None:
                return True
        return self._virtual.move_window(identifier, x, y, width, height, repaint=repaint)

    def close_window(self, identifier: str | int) -> bool:
        if self._has_wmctrl:
            target = hex(identifier) if isinstance(identifier, int) else str(identifier)
            if self._run_cmd(["wmctrl", "-i", "-c", target]) is not None:
                return True
        return self._virtual.close_window(identifier)

    def client_to_screen(self, hwnd: int, client_x: int, client_y: int) -> tuple[int, int]:
        win = self.get_window_by_hwnd(hwnd)
        if win:
            return win.x + client_x, win.y + client_y
        return client_x, client_y

    def screen_to_client(self, hwnd: int, screen_x: int, screen_y: int) -> tuple[int, int]:
        win = self.get_window_by_hwnd(hwnd)
        if win:
            return screen_x - win.x, screen_y - win.y
        return screen_x, screen_y

    def get_window_rect(self, hwnd: int) -> tuple[int, int, int, int] | None:
        win = self.get_window_by_hwnd(hwnd)
        if win:
            return (win.x, win.y, win.x + win.width, win.y + win.height)
        return None


def get_default_desktop_backend() -> DesktopBackend:
    """Select the appropriate desktop backend for the host operating system."""
    if IS_WINDOWS:
        return Win32DesktopBackend()
    if sys.platform.startswith("linux"):
        return LinuxDesktopBackend()
    return HeadlessDesktopBackend()
