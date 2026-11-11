"""
services/startup_service.py — Windows Startup Registry Manager for PowerShellStore

Manages automatic startup on Windows user login via:
  HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REG_NAME = "PowerShellStore"


class StartupService:
    def __init__(self, main_script_path: Path | str | None = None) -> None:
        if main_script_path is None:
            self.main_script_path = (Path(__file__).resolve().parent.parent / "main.py").resolve()
        else:
            self.main_script_path = Path(main_script_path).resolve()

    def get_launch_command(self, argument: str = "--startup") -> str:
        """
        Constructs the Windows command to launch PowerShellStore.
        Prefers pythonw.exe over python.exe to suppress console windows on login.
        """
        py_dir = Path(sys.executable).parent
        pythonw = py_dir / "pythonw.exe"
        exe_path = str(pythonw if pythonw.exists() else sys.executable)
        arg_suffix = f" {argument}" if argument else ""
        return f'"{exe_path}" "{self.main_script_path}"{arg_suffix}'

    def is_startup_enabled(self) -> bool:
        """Checks if PowerShellStore is registered to run on Windows startup."""
        if sys.platform != "win32":
            return False

        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REG_RUN_KEY,
                0,
                winreg.KEY_READ,
            ) as key:
                val, _ = winreg.QueryValueEx(key, APP_REG_NAME)
                return bool(val)
        except (FileNotFoundError, OSError):
            return False

    def enable_startup(self, argument: str = "--startup") -> bool:
        """Registers PowerShellStore in HKCU Run key."""
        if sys.platform != "win32":
            logger.warning("Windows startup registration only supported on win32.")
            return False

        import winreg

        command = self.get_launch_command(argument)
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REG_RUN_KEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(key, APP_REG_NAME, 0, winreg.REG_SZ, command)
                logger.info("Enabled Windows startup for PowerShellStore: %s", command)
                return True
        except OSError as exc:
            logger.error("Failed to enable Windows startup: %s", exc)
            return False

    def disable_startup(self) -> bool:
        """Removes PowerShellStore from HKCU Run key."""
        if sys.platform != "win32":
            return False

        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REG_RUN_KEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, APP_REG_NAME)
                logger.info("Disabled Windows startup for PowerShellStore.")
                return True
        except FileNotFoundError:
            # Already disabled
            return True
        except OSError as exc:
            logger.error("Failed to disable Windows startup: %s", exc)
            return False

    def toggle_startup(self, enable: bool, argument: str = "--startup") -> bool:
        """Toggles startup registration based on the boolean flag."""
        return self.enable_startup(argument) if enable else self.disable_startup()

