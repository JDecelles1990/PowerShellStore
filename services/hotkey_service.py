"""
services/hotkey_service.py — Global Windows Hotkey Manager for PowerShellStore

Registers and listens for the system-wide 'Shift+F8' keyboard shortcut
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

DEFAULT_HOTKEY_ID = 0x5053  # Unique hotkey ID ('PS')


def bring_window_to_foreground(hwnd: int) -> bool:
    """Brings the specified native window to the foreground on Windows."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        user32 = ctypes.windll.user32
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception as exc:
        logger.debug("Failed to set foreground window: %s", exc)
        return False


class _NativeHotkeyEventFilter(QAbstractNativeEventFilter, QObject):
    """Native event filter that catches WM_HOTKEY messages on the Windows message loop."""

    hotkey_pressed = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    def nativeEventFilter(self, event_type: Any, message: Any) -> tuple[bool, int]:
        # On Windows, event_type is b"windows_generic_MSG" or b"windows_dispatcher_MSG"
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    hotkey_id = int(msg.wParam)
                    self.hotkey_pressed.emit(hotkey_id)
                    return True, 0
            except Exception as exc:
                logger.debug("Error processing native event message: %s", exc)

        return False, 0


class GlobalHotkeyManager(QObject):
    """
    Manages global registration of Shift+F8 shortcut across all Windows applications.
    Emits `triggered` signal whenever Shift+F8 is pressed anywhere in the OS.
    """

    triggered = Signal()

    def __init__(
        self,
        hotkey_id: int = DEFAULT_HOTKEY_ID,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.hotkey_id = hotkey_id
        self._hwnd: int | None = None
        self._is_registered: bool = False
        self._event_filter: _NativeHotkeyEventFilter | None = None

    @property
    def is_registered(self) -> bool:
        return self._is_registered

    def register(self, hwnd: int) -> bool:
        """
        Registers Shift+F8 with Windows using the provided window handle.
        """
        if sys.platform != "win32":
            logger.warning("Global hotkeys only supported on Windows.")
            return False

        if self._is_registered:
            logger.debug("Hotkey %d already registered.", self.hotkey_id)
            return True

        self._hwnd = hwnd
        user32 = ctypes.windll.user32

        # Shift + F8 with MOD_NOREPEAT to prevent keyboard key-repeat spam
        modifiers = MOD_SHIFT | MOD_NOREPEAT
        res = user32.RegisterHotKey(self._hwnd, self.hotkey_id, modifiers, VK_F8)

        if not res:
            err = ctypes.GetLastError()
            logger.warning(
                "RegisterHotKey(Shift+F8) failed with Win32 Error %d (already in use or sandboxed).",
                err,
            )
            # Try without MOD_NOREPEAT as fallback on older Windows kernels
            res = user32.RegisterHotKey(self._hwnd, self.hotkey_id, MOD_SHIFT, VK_F8)

        if res:
            self._is_registered = True
            logger.info("Successfully registered global shortcut Shift+F8 (ID: %d).", self.hotkey_id)

            # Install native event filter on QApplication
            app = QCoreApplication.instance()
            if app and not self._event_filter:
                self._event_filter = _NativeHotkeyEventFilter(self)
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
        logger.info("Unregistered global shortcut Shift+F8.")
        return bool(res)

    def _on_hotkey_received(self, hotkey_id: int) -> None:
        if hotkey_id == self.hotkey_id:
            logger.debug("Global hotkey Shift+F8 triggered.")
            self.triggered.emit()
