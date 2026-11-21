from unittest.mock import MagicMock

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication
import pytest

from repositories.catalog_repo import CatalogRepo
from services.hotkey_service import GlobalHotkeyManager
from services.startup_service import StartupService
from ui.backdrop_fx import (
    BACKDROP_FX_PROPERTY,
    BACKDROP_PANEL_NAMES,
    BackdropFx,
    install_backdrop_fx,
)
from ui.launcher_view import LauncherView
from ui.styles import DARK_THEME_QSS


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, fx: BackdropFx, seconds: float, step: float = 0.03) -> None:
        elapsed = 0.0
        while elapsed < seconds:
            self.t += step
            elapsed += step
            fx._tick()


def _make_window(tmp_path) -> LauncherView:
    repo = CatalogRepo(tmp_path / "backdrop_test.db")
    mock_startup = MagicMock(spec=StartupService)
    mock_startup.is_startup_enabled.return_value = False
    mock_hotkey = MagicMock(spec=GlobalHotkeyManager)

    window = LauncherView(
        repo=repo,
        startup_service=mock_startup,
        hotkey_manager=mock_hotkey,
    )
    window.setStyleSheet(DARK_THEME_QSS)
    return window


def test_launcher_view_installs_backdrop_and_glass_overlays_idempotently(qapp, tmp_path):
    window = _make_window(tmp_path)
    try:
        fx = window.backdrop_fx
        assert isinstance(fx, BackdropFx)
        assert window.property(BACKDROP_FX_PROPERTY) is fx
        assert install_backdrop_fx(window) is fx
        assert set(fx.panel_overlays.keys()) == set(BACKDROP_PANEL_NAMES)

        # Canvas & overlays are click-through and don't steal keyboard focus
        assert fx.canvas.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert fx.canvas.focusPolicy() == Qt.FocusPolicy.NoFocus
        for overlay in fx.panel_overlays.values():
            assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            assert overlay.focusPolicy() == Qt.FocusPolicy.NoFocus
    finally:
        window._force_quit = True
        window.close()


def test_dynamic_gradient_backdrop_renders_and_animates_colors(qapp, tmp_path):
    window = _make_window(tmp_path)
    try:
        window.resize(1200, 760)
        fx = window.backdrop_fx
        clock = FakeClock()
        fx._now = clock
        fx._canvas.resize(window.centralWidget().size())

        img_t0 = fx.canvas.grab().toImage()
        clock.advance(fx, 4.0)
        img_t1 = fx.canvas.grab().toImage()

        assert not img_t0.isNull() and not img_t1.isNull()

        hues: set[int] = set()
        changed_pixels = 0
        for y in range(20, img_t0.height(), 36):
            for x in range(20, img_t0.width(), 44):
                c0 = img_t0.pixelColor(x, y)
                c1 = img_t1.pixelColor(x, y)
                if c0.saturation() > 30:
                    hues.add(c0.hsvHue() // 25)
                if c0.rgb() != c1.rgb():
                    changed_pixels += 1

        assert len(hues) >= 3, f"Expected multi-hue aurora backdrop, got hue buckets: {hues}"
        assert changed_pixels > 50, "Expected dynamic gradient backdrop colors to animate over time"
    finally:
        window._force_quit = True
        window.close()


def test_interactive_mouse_hover_glass_spotlight_and_panel_transitions(qapp, tmp_path):
    window = _make_window(tmp_path)
    try:
        window.resize(1360, 840)
        # Force Qt layout calculation cleanly without calling window.show()
        window.grab()

        fx = window.backdrop_fx
        clock = FakeClock()
        fx._now = clock

        sidebar_pos = QPointF(window.sidebar.mapTo(window.centralWidget(), window.sidebar.rect().center()))
        inspector_pos = QPointF(window.inspector_frame.mapTo(window.centralWidget(), window.inspector_frame.rect().center()))

        # Hover over SidebarFrame -> smoothly ramps to 1.0 while Inspector stays 0.0
        fx.set_cursor_pos(sidebar_pos)
        clock.advance(fx, 0.45)
        assert fx.panel_hover_level("SidebarFrame") == pytest.approx(1.0)
        assert fx.panel_hover_level("InspectorFrame") == 0.0
        assert not fx.panel_overlays["SidebarFrame"].grab().isNull()

        # Move cursor to InspectorFrame -> Sidebar decays while Inspector ramps to 1.0
        fx.set_cursor_pos(inspector_pos)
        clock.advance(fx, 0.55)
        assert fx.panel_hover_level("InspectorFrame") == pytest.approx(1.0)
        assert fx.panel_hover_level("SidebarFrame") == 0.0
        assert not fx.panel_overlays["InspectorFrame"].grab().isNull()

        # Clear cursor -> all panel hover levels decay cleanly back to 0.0 & timer stops
        fx.clear_cursor()
        clock.advance(fx, 0.65)
        assert fx.panel_hover_level("InspectorFrame") == 0.0
        assert fx.panel_hover_level("SidebarFrame") == 0.0
        assert not fx.is_active
    finally:
        window._force_quit = True
        window.close()


def test_frosted_glass_stylesheet_preserves_all_button_styles():
    # Panels use translucent rgba() glass surfaces
    assert "rgba(15, 23, 42, 0.58)" in DARK_THEME_QSS
    # All push button rules and gradients remain intact
    for selector in (
        "QPushButton:hover",
        "QPushButton:pressed",
        "QPushButton#PrimaryButton:hover",
        "QPushButton#SuccessButton:hover",
        "QPushButton#DangerButton:hover",
        "QPushButton#ReportButton:hover",
    ):
        assert selector in DARK_THEME_QSS
    assert DARK_THEME_QSS.count("qlineargradient") >= 10
