from pathlib import Path
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication
import pytest

from services.startup_service import StartupService
from services.hotkey_service import GlobalHotkeyManager, DEFAULT_HOTKEY_ID
from ui.sidebar_view import SidebarView
from ui.launcher_view import LauncherView


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_startup_service_launch_command():
    service = StartupService()
    cmd = service.get_launch_command("--startup")
    assert "main.py" in cmd
    assert "--startup" in cmd
    assert cmd.startswith('"')


def test_startup_service_enable_disable_mocked():
    service = StartupService()

    with patch("winreg.OpenKey"), patch("winreg.SetValueEx") as mock_set, patch("winreg.QueryValueEx", return_value=("test_cmd", 1)):
        assert service.enable_startup() is True
        mock_set.assert_called_once()
        assert service.is_startup_enabled() is True

    with patch("winreg.OpenKey"), patch("winreg.DeleteValue") as mock_del:
        assert service.disable_startup() is True
        mock_del.assert_called_once()


def test_hotkey_manager_initialization():
    manager = GlobalHotkeyManager()
    assert manager.hotkey_id == DEFAULT_HOTKEY_ID
    assert manager.is_registered is False


def test_sidebar_startup_checkbox(qapp):
    sidebar = SidebarView()
    assert hasattr(sidebar, "startup_checkbox")
    assert sidebar.startup_checkbox.text() == "Start with Windows"

    # Test programmatic check without signal loop
    sidebar.set_startup_checked(True)
    assert sidebar.startup_checkbox.isChecked() is True

    sidebar.set_startup_checked(False)
    assert sidebar.startup_checkbox.isChecked() is False


def test_launcher_view_hotkey_and_startup_wiring(qapp):
    mock_startup = MagicMock(spec=StartupService)
    mock_startup.is_startup_enabled.return_value = True

    mock_hotkey = MagicMock(spec=GlobalHotkeyManager)
    mock_hotkey.is_registered = False

    window = LauncherView(
        startup_service=mock_startup,
        hotkey_manager=mock_hotkey,
    )

    # Verify startup checkbox reflects mock service state
    assert window.sidebar.startup_checkbox.isChecked() is True
    assert window.hotkey_manager is not None
    assert hasattr(window, "tray_icon")
    assert window.tray_icon.toolTip() == "PowerShellStore — Press Shift+F8 to Open"

    window._force_quit = True
    window.close()
