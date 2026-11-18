from ctypes import addressof, wintypes
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication
import pytest

from services.startup_service import StartupService
from services.hotkey_service import (
    DEFAULT_HOTKEY_ID,
    DEFAULT_HOTKEY_LABEL,
    MOD_NOREPEAT,
    MOD_WIN,
    VK_F8,
    WM_HOTKEY,
    GlobalHotkeyManager,
)
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


def test_hotkey_manager_initialization_and_win_f8_registration(qapp):
    manager = GlobalHotkeyManager()
    assert manager.hotkey_id == DEFAULT_HOTKEY_ID
    assert manager.modifiers == MOD_WIN
    assert manager.vk == VK_F8
    assert manager.shortcut_label == DEFAULT_HOTKEY_LABEL == "Win+F8"
    assert manager.is_registered is False

    # Verify RegisterHotKey receives MOD_WIN | MOD_NOREPEAT and VK_F8
    with patch("ctypes.windll.user32.RegisterHotKey", return_value=1) as mock_reg, \
         patch("ctypes.windll.user32.UnregisterHotKey", return_value=1) as mock_unreg:
        assert manager.register(12345) is True
        assert manager.is_registered is True
        mock_reg.assert_called_once_with(12345, DEFAULT_HOTKEY_ID, MOD_WIN | MOD_NOREPEAT, VK_F8)

        # Simulate OS WM_HOTKEY message dispatch through the native event filter
        triggered_count = 0
        def _on_trigger():
            nonlocal triggered_count
            triggered_count += 1

        manager.triggered.connect(_on_trigger)
        msg = wintypes.MSG()
        msg.message = WM_HOTKEY
        msg.wParam = DEFAULT_HOTKEY_ID
        handled, _ = manager._event_filter.nativeEventFilter(b"windows_generic_MSG", addressof(msg))
        assert handled is True
        assert triggered_count == 1

        assert manager.unregister() is True
        assert manager.is_registered is False
        mock_unreg.assert_called_once_with(12345, DEFAULT_HOTKEY_ID)


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
    assert window.tray_icon.toolTip() == "PowerShellStore — Press Win+F8 to Open or Minimize"
    assert window.action_tray_toggle.text() == "Show / Minimize PowerShellStore (Win+F8)"

    window._force_quit = True
    window.close()


def test_launcher_view_toggle_shows_and_minimizes(qapp):
    mock_startup = MagicMock(spec=StartupService)
    mock_startup.is_startup_enabled.return_value = False
    mock_hotkey = MagicMock(spec=GlobalHotkeyManager)

    window = LauncherView(
        startup_service=mock_startup,
        hotkey_manager=mock_hotkey,
    )

    with patch("ui.launcher_view.bring_window_to_foreground"), \
         patch.object(window, "show") as mock_show, \
         patch.object(window, "showMinimized") as mock_minimize:
        # 1. Hidden -> brings app onto screen
        with patch.object(window, "isHidden", return_value=True), \
             patch.object(window, "isMinimized", return_value=False), \
             patch.object(window, "isActiveWindow", return_value=False):
            window.toggle_window_visibility()
            mock_show.assert_called_once()
            mock_minimize.assert_not_called()

        mock_show.reset_mock()
        mock_minimize.reset_mock()

        # 2. Visible & active -> minimizes window
        with patch.object(window, "isHidden", return_value=False), \
             patch.object(window, "isMinimized", return_value=False), \
             patch.object(window, "isActiveWindow", return_value=True):
            window.toggle_window_visibility()
            mock_minimize.assert_called_once()
            mock_show.assert_not_called()

        mock_show.reset_mock()
        mock_minimize.reset_mock()

        # 3. Minimized -> restores back onto screen
        with patch.object(window, "isHidden", return_value=False), \
             patch.object(window, "isMinimized", return_value=True), \
             patch.object(window, "isActiveWindow", return_value=False):
            window.toggle_window_visibility()
            mock_show.assert_called_once()
            mock_minimize.assert_not_called()

    window._force_quit = True
    window.close()
