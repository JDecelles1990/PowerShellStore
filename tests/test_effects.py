from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QListWidget, QPushButton, QTableWidget, QTableWidgetItem, QWidget, QHBoxLayout
import pytest

from ui.effects import (
    FX_PROPERTY,
    ButtonFx,
    GlowItemDelegate,
    install_button_fx,
    install_item_view_glow,
    install_item_view_glow_recursive,
)
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

    def advance(self, fx, seconds: float, step: float = 0.016) -> None:
        elapsed = 0.0
        while elapsed < seconds:
            self.t += step
            elapsed += step
            fx._tick()


def test_stylesheet_has_gradient_hover_and_pressed_states():
    for selector in ("QPushButton:hover", "QPushButton:pressed", "QPushButton#PrimaryButton:hover",
                     "QPushButton#SuccessButton:hover", "QPushButton#DangerButton:hover",
                     "QPushButton#ReportButton:hover"):
        assert selector in DARK_THEME_QSS
    assert DARK_THEME_QSS.count("qlineargradient") >= 10


def test_button_fx_hover_glow_click_and_cleanup(qapp):
    host = QWidget()
    host.setStyleSheet(DARK_THEME_QSS)
    layout = QHBoxLayout(host)
    button = QPushButton("Glow Me", host)
    button.setObjectName("PrimaryButton")
    layout.addWidget(button)
    host.resize(240, 80)

    fx = ButtonFx(button)
    clock = FakeClock()
    fx._now = clock
    assert button.property(FX_PROPERTY) is True

    # Hover: glow fades in and a QGraphicsDropShadowEffect is attached
    fx.set_hovered(True)
    clock.advance(fx, 0.4)
    assert fx.hover_level == pytest.approx(1.0)
    assert button.graphicsEffect() is not None
    assert fx.is_active
    assert not host.grab().isNull()  # exercises gloss, rim and sweep painting

    # Click: burst + ripple
    fx.trigger_click(QPointF(10, 10))
    clock.advance(fx, 0.1)
    assert fx._burst > 0.0 and fx._ripples
    assert not host.grab().isNull()

    # Leave: everything fades out, effect removed, timer stopped
    fx.set_hovered(False)
    clock.advance(fx, 1.5)
    assert fx.hover_level == 0.0
    assert button.graphicsEffect() is None
    assert not fx.is_active


def test_button_fx_ignores_disabled_buttons(qapp):
    button = QPushButton("Disabled")
    button.setEnabled(False)
    fx = ButtonFx(button)
    fx.set_hovered(True)
    assert fx._hovered is False


def test_install_button_fx_is_idempotent(qapp):
    assert install_button_fx(qapp) is install_button_fx(qapp)


def test_glow_delegate_on_list_and_table(qapp):
    lst = QListWidget()
    lst.setStyleSheet(DARK_THEME_QSS)
    lst.addItems(["All Scripts (38)", "System (11)", "Network (6)"])
    lst.resize(220, 160)

    delegate = install_item_view_glow(lst)
    assert isinstance(delegate, GlowItemDelegate)
    assert install_item_view_glow(lst) is delegate  # idempotent
    clock = FakeClock()
    delegate._now = clock

    delegate.set_hover_row(1)
    clock.advance(delegate, 0.3, step=0.03)
    assert delegate.row_level(1) == pytest.approx(1.0)
    delegate.trigger_click(1, QPointF(40, 30))
    clock.advance(delegate, 0.1, step=0.03)
    assert not lst.grab().isNull()

    delegate.set_hover_row(-1)
    clock.advance(delegate, 1.0, step=0.03)
    assert delegate.row_level(1) == 0.0
    assert not delegate._timer.isActive()

    table = QTableWidget(2, 3)
    for r in range(2):
        for c in range(3):
            table.setItem(r, c, QTableWidgetItem(f"r{r}c{c}"))
    table_delegate = install_item_view_glow(table)
    table_delegate._now = clock
    table_delegate.set_hover_row(0)
    clock.advance(table_delegate, 0.3, step=0.03)
    assert not table.grab().isNull()


def test_launcher_view_installs_item_glow(qapp, tmp_path):
    from repositories.catalog_repo import CatalogRepo
    from ui.launcher_view import LauncherView

    repo = CatalogRepo(tmp_path / "fx.db")
    window = LauncherView(repo=repo)
    views = {type(d._view).__name__ for d in window.item_view_glow}
    assert "QListWidget" in views
    assert "QTableWidget" in views
    # Combo-box popup lists must be left alone
    assert window.sidebar.risk_combo.view().itemDelegate() not in window.item_view_glow
    # Re-running is idempotent
    assert len(install_item_view_glow_recursive(window)) == len(window.item_view_glow)
    window._force_quit = True
    window.close()

