"""
services/hotkey_service.py — Global Windows Hotkey Manager for PowerShellStore

Registers and listens for the system-wide 'Win+F8' keyboard shortcut
using Windows RegisterHotKey API and PySide6 QAbstractNativeEventFilter.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from typing import Any

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

logger = logging.getLogger(__name__)

# Windows API Constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_F8 = 0x77  # Virtual-Key code for F8 (119)
WM_HOTKEY = 0x0312
SW_SHOW = 5
SW_RESTORE = 9

DEFAULT_HOTKEY_ID = 0x5053  # Unique hotkey ID ('PS')
DEFAULT_MODIFIERS = MOD_WIN
DEFAULT_VK = VK_F8
DEFAULT_HOTKEY_LABEL = "Win+F8"


def bring_window_to_foreground(hwnd: int) -> bool:
    """Restores (if minimized) and brings the specified native window to the foreground on Windows."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        user32 = ctypes.windll.user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)
        user32.BringWindowToTop(hwnd)
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception as exc:
        logger.debug("Failed to set foreground window: %s", exc)
        return False


class _NativeHotkeyEventFilter(QObject, QAbstractNativeEventFilter):
    """Native event filter that catches WM_HOTKEY messages on the Windows message loop."""

    hotkey_pressed = Signal(int)

    def __init__(self, expected_hotkey_id: int | None = None, parent: QObject | None = None) -> None:
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self._expected_hotkey_id = expected_hotkey_id

    def nativeEventFilter(self, event_type: Any, message: Any) -> tuple[bool, int]:
        # On Windows, event_type is b"windows_generic_MSG" or b"windows_dispatcher_MSG"
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    hotkey_id = int(msg.wParam)
                    if self._expected_hotkey_id is None or hotkey_id == self._expected_hotkey_id:
                        self.hotkey_pressed.emit(hotkey_id)
                        return True, 0
            except Exception as exc:
                logger.debug("Error processing native event message: %s", exc)

        return False, 0


class GlobalHotkeyManager(QObject):
    """
    Manages global registration of Win+F8 shortcut across all Windows applications.
    Emits `triggered` signal whenever Win+F8 is pressed anywhere in the OS.
    """

    triggered = Signal()

    def __init__(
        self,
        hotkey_id: int = DEFAULT_HOTKEY_ID,
        modifiers: int = DEFAULT_MODIFIERS,
        vk: int = DEFAULT_VK,
        shortcut_label: str = DEFAULT_HOTKEY_LABEL,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.hotkey_id = hotkey_id
        self.modifiers = modifiers
        self.vk = vk
        self.shortcut_label = shortcut_label
        self._hwnd: int | None = None
        self._is_registered: bool = False
        self._event_filter: _NativeHotkeyEventFilter | None = None

    @property
    def is_registered(self) -> bool:
        return self._is_registered

    def register(self, hwnd: int) -> bool:
        """
        Registers Win+F8 with Windows using the provided window handle.
        """
        if sys.platform != "win32":
            logger.warning("Global hotkeys only supported on Windows.")
            return False

        if self._is_registered:
            logger.debug("Hotkey %d already registered.", self.hotkey_id)
            return True

        self._hwnd = hwnd
        user32 = ctypes.windll.user32

        # Win + F8 with MOD_NOREPEAT to prevent keyboard key-repeat spam
        res = user32.RegisterHotKey(self._hwnd, self.hotkey_id, self.modifiers | MOD_NOREPEAT, self.vk)

        if not res:
            err = ctypes.GetLastError()
            logger.warning(
                "RegisterHotKey(%s) with MOD_NOREPEAT failed with Win32 Error %d (already in use or sandboxed).",
                self.shortcut_label,
                err,
            )
            # Fallback without MOD_NOREPEAT on older Windows kernels
            res = user32.RegisterHotKey(self._hwnd, self.hotkey_id, self.modifiers, self.vk)

        if res:
            self._is_registered = True
            logger.info("Successfully registered global shortcut %s (ID: %d).", self.shortcut_label, self.hotkey_id)

            # Install native event filter on QApplication
            app = QCoreApplication.instance()
            if app and not self._event_filter:
                self._event_filter = _NativeHotkeyEventFilter(self.hotkey_id, self)
                self._event_filter.hotkey_pressed.connect(self._on_hotkey_received)
                app.installNativeEventFilter(self._event_filter)
            return True

        return False

    def unregister(self) -> bool:
        """Unregisters the hotkey and removes the native event filter."""
        if not self._is_registered or not self._hwnd or sys.platform != "win32":
            return False

        user32 = ctypes.windll.user32
        res = user32.UnregisterHotKey(self._hwnd, self.hotkey_id)

        app = QCoreApplication.instance()
        if app and self._event_filter:
            app.removeNativeEventFilter(self._event_filter)
            self._event_filter = None

        self._is_registered = False
        logger.info("Unregistered global shortcut %s.", self.shortcut_label)
        return bool(res)

    def _on_hotkey_received(self, hotkey_id: int) -> None:
        if hotkey_id == self.hotkey_id:
            logger.debug("Global hotkey %s triggered.", self.shortcut_label)
            self.triggered.emit()
