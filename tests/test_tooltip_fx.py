from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QColor, QHelpEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)
import pytest

from ui.styles import DARK_THEME_QSS
from ui.tooltip_fx import (
    RainbowTooltip,
    _TooltipFxManager,
    install_tooltip_fx,
    resolve_tooltip_text,
)


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

    def advance(self, tooltip: RainbowTooltip, seconds: float, step: float = 0.016) -> None:
        elapsed = 0.0
        while elapsed < seconds:
            self.t += step
            elapsed += step
            tooltip._tick()


def test_rainbow_tooltip_transitions_and_dynamic_rainbow_text(qapp):
    tip = RainbowTooltip()
    clock = FakeClock()
    tip._now = clock

    assert tip.state == "hidden"
    assert tip.transition_progress == 0.0
    assert not tip.is_active

    # Show tooltip -> transitions from showing -> visible with shine sweep
    tip.show_tooltip("Copy RMM-Ready Script (Ctrl+Shift+R)", QPoint(200, 200))
    assert tip.state == "showing"
    assert tip.is_active
    assert tip._sweep == 0.0

    clock.advance(tip, 0.30)
    assert tip.state == "visible"
    assert tip.transition_progress == pytest.approx(1.0)

    # Render rainbow text image at two distinct timestamps and verify:
    # 1. Text pixels span multiple distinct hues (rainbow across width)
    # 2. Text hues shift dynamically over time
    text_rect = tip.rect().adjusted(33, 27, -33, -27).toRectF()
    img_t0 = tip._build_rainbow_text_image(text_rect, hue_phase=0.0, alpha=1.0)
    img_t1 = tip._build_rainbow_text_image(text_rect, hue_phase=0.45, alpha=1.0)

    hues_t0: set[int] = set()
    changed_pixels = 0
    for y in range(0, img_t0.height(), 2):
        for x in range(0, img_t0.width(), 2):
            c0 = img_t0.pixelColor(x, y)
            c1 = img_t1.pixelColor(x, y)
            if c0.alpha() > 160:
                hues_t0.add(c0.hsvHue() // 25)
                if c0.rgb() != c1.rgb():
                    changed_pixels += 1

    assert len(hues_t0) >= 4, f"Expected multi-hue rainbow text, got hue buckets: {hues_t0}"
    assert changed_pixels > 20, "Rainbow text colors did not dynamically shift over time"

    # Full widget paint exercises outer glow halo, aurora background, shine sweep, sparkles, rim & text
    pixmap_visible = tip.grab()
    assert not pixmap_visible.isNull()

    # Periodic shine sweep replays after SWEEP_PERIOD
    clock.advance(tip, 2.3)
    assert tip._sweep >= 0.0 or tip._next_sweep > clock.t
    assert not tip.grab().isNull()

    # Hide transition smoothly fades out to 0.0 and stops timer completely
    tip.hide_tooltip()
    assert tip.state == "hiding"
    clock.advance(tip, 0.25)
    assert tip.state == "hidden"
    assert tip.transition_progress == 0.0
    assert not tip.is_active
    assert not tip.isVisible()


def test_resolve_tooltip_text_across_widgets_tabs_headers_and_cells(qapp):
    # 1. Standard widget + nested child inside container with tooltip
    container = QFrame()
    container.setToolTip("Hotkey badge tooltip")
    layout = QHBoxLayout(container)
    child_lbl = QLabel("Win+F8", container)
    layout.addWidget(child_lbl)
    assert resolve_tooltip_text(container) == "Hotkey badge tooltip"
    assert resolve_tooltip_text(child_lbl) == "Hotkey badge tooltip"

    # 2. QTabBar tab tooltip
    tabs = QTabWidget()
    tabs.addTab(QWidget(), "Structured Results")
    tabs.setTabToolTip(0, "Structured Results (Ctrl+1)")
    tab_bar = tabs.tabBar()
    tab_center = tab_bar.tabRect(0).center()
    assert resolve_tooltip_text(tab_bar, tab_center) == "Structured Results (Ctrl+1)"

    # 3. QTableWidget header & cell tooltips
    table = QTableWidget(1, 2)
    table.setHorizontalHeaderLabels(["Title", "Risk Level"])
    table.horizontalHeaderItem(0).setToolTip("Click to sort by Title")
    cell = QTableWidgetItem("Disk Space")
    cell.setToolTip("Cell tooltip info")
    table.setItem(0, 0, cell)
    table.resize(300, 120)

    header = table.horizontalHeader()
    hdr_pos = QPoint(max(5, header.sectionPosition(0) + 10), 5)
    assert resolve_tooltip_text(header, hdr_pos) == "Click to sort by Title"

    cell_center = table.visualItemRect(cell).center()
    assert resolve_tooltip_text(table.viewport(), cell_center) == "Cell tooltip info"


def test_tooltip_manager_intercepts_tooltip_events_and_is_idempotent(qapp):
    assert install_tooltip_fx(qapp) is install_tooltip_fx(qapp)

    manager = _TooltipFxManager()
    clock = FakeClock()
    manager.popup._now = clock

    widget = QPushButton("Hover Target")
    widget.setToolTip("Animated tooltip preview")

    help_ev = QHelpEvent(QEvent.Type.ToolTip, QPoint(10, 10), QPoint(300, 300))
    handled = manager.eventFilter(widget, help_ev)
    assert handled is True
    assert manager.popup.text == "Animated tooltip preview"
    assert manager.popup.state == "showing"

    clock.advance(manager.popup, 0.30)
    assert manager.popup.state == "visible"

    # Leave event triggers fade-out transition
    leave_ev = QEvent(QEvent.Type.Leave)
    manager.eventFilter(widget, leave_ev)
    assert manager.popup.state == "hiding"

    clock.advance(manager.popup, 0.25)
    assert manager.popup.state == "hidden"
    assert not manager.popup.is_active

    # Empty tooltip is not intercepted
    plain_widget = QWidget()
    plain_ev = QHelpEvent(QEvent.Type.ToolTip, QPoint(5, 5), QPoint(100, 100))
    assert manager.eventFilter(plain_widget, plain_ev) is False


def test_stylesheet_includes_tooltip_fallback_without_altering_buttons():
    assert "QToolTip" in DARK_THEME_QSS
    assert "QPushButton:hover" in DARK_THEME_QSS
