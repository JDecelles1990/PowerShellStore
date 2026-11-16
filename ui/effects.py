"""Animated hover / click effects for PowerShellStore.

Provides two pieces of eye-candy on top of the static QSS gradients in ``ui/styles.py``:

* ``ButtonFx`` — attached lazily to every ``QPushButton`` the first time the mouse enters it.
  While hovered the button gets a rainbow-cycling outer glow (``QGraphicsDropShadowEffect``),
  a glossy highlight, an animated rainbow rim and a periodic diagonal "shine" sweep.
  Clicking fires a glow burst plus an expanding light ripple from the cursor position.

* ``GlowItemDelegate`` — an item delegate for lists / tables. The hovered row is painted as a
  glowing gradient "button" (rainbow fill, inner glow, bright rim) and clicks emit a ripple.

Effects are only active while something is animating; idle widgets carry no graphics effect
and no running timers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import shiboken6
from PySide6.QtCore import QElapsedTimer, QEvent, QObject, QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QGraphicsDropShadowEffect,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QWidget,
)

FX_PROPERTY = "_psstore_fx_attached"

BUTTON_FRAME_MS = 16       # ~60 fps for buttons
LIST_FRAME_MS = 30         # ~33 fps for list/table rows (cheaper full-viewport repaints)
HUE_SPEED = 0.18           # rainbow cycles per second
RIPPLE_SECONDS = 0.55
SWEEP_SECONDS = 0.65
SWEEP_PERIOD = 2.4         # seconds between shine sweeps while hovering


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _hue_phase() -> float:
    return (time.monotonic() * HUE_SPEED) % 1.0


def _rainbow(offset: float, sat: float = 0.85, val: float = 1.0, alpha: float = 1.0) -> QColor:
    """Returns a colour on the animated rainbow wheel, shifted by ``offset`` (0..1)."""
    return QColor.fromHsvF((_hue_phase() + offset) % 1.0, sat, val, max(0.0, min(1.0, alpha)))


def _approach(current: float, target: float, rate: float, dt: float) -> float:
    step = rate * dt
    if current < target:
        return min(target, current + step)
    return max(target, current - step)


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor.fromRgbF(
        a.redF() + (b.redF() - a.redF()) * t,
        a.greenF() + (b.greenF() - a.greenF()) * t,
        a.blueF() + (b.blueF() - a.blueF()) * t,
        a.alphaF() + (b.alphaF() - a.alphaF()) * t,
    )


@dataclass
class _Ripple:
    center: QPointF
    started: float
    row: int = -1


def _paint_ripples(painter: QPainter, ripples: list[_Ripple], now: float, max_radius: float) -> None:
    for ripple in ripples:
        t = (now - ripple.started) / RIPPLE_SECONDS
        if not 0.0 <= t < 1.0:
            continue
        radius = max(1.0, max_radius * _ease_out(t))
        fade = 1.0 - t
        grad = QRadialGradient(ripple.center, radius)
        grad.setColorAt(0.0, QColor(255, 255, 255, int(170 * fade)))
        grad.setColorAt(0.55, _rainbow(0.1, 0.55, 1.0, 0.45 * fade))
        grad.setColorAt(0.85, _rainbow(0.4, 0.75, 1.0, 0.25 * fade))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(ripple.center, radius, radius)


# ---------------------------------------------------------------------------
# Push buttons
# ---------------------------------------------------------------------------
class _ButtonOverlay(QWidget):
    """Transparent child widget painted on top of a button (gloss, rim, sweep, ripples)."""

    def __init__(self, fx: "ButtonFx", button: QPushButton) -> None:
        super().__init__(button)
        self._fx = fx
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background: transparent; border: none;")
        self.setGeometry(button.rect())
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        try:
            self._fx.paint_overlay(painter, QRectF(self.rect()))
        finally:
            painter.end()


class ButtonFx(QObject):
    """Hover glow, shine sweep and click ripple for a single QPushButton."""

    def __init__(self, button: QPushButton) -> None:
        super().__init__(button)
        self._button = button
        self._hovered = False
        self._hover = 0.0          # 0..1 hover intensity (eased)
        self._burst = 0.0          # 0..1 click burst intensity (decays)
        self._sweep = -1.0         # <0 = inactive, otherwise sweep progress 0..1
        self._next_sweep = 0.0
        self._ripples: list[_Ripple] = []
        self._effect: QGraphicsDropShadowEffect | None = None

        self._clock = QElapsedTimer()
        self._clock.start()
        self._last = self._now()

        self._overlay = _ButtonOverlay(self, button)
        self._timer = QTimer(self)
        self._timer.setInterval(BUTTON_FRAME_MS)
        self._timer.timeout.connect(self._tick)

        button.setProperty(FX_PROPERTY, True)
        button.installEventFilter(self)

    # -- state -------------------------------------------------------------
    def _now(self) -> float:
        return self._clock.elapsed() / 1000.0

    @property
    def is_active(self) -> bool:
        return self._timer.isActive()

    @property
    def hover_level(self) -> float:
        return self._hover

    def set_hovered(self, hovered: bool) -> None:
        if hovered and not self._button.isEnabled():
            return
        now = self._now()
        if hovered and not self._hovered:
            self._sweep = 0.0
            self._next_sweep = now + SWEEP_PERIOD
        self._hovered = hovered
        self._start()

    def trigger_click(self, pos: QPointF | None = None) -> None:
        center = QPointF(pos) if pos is not None else QRectF(self._button.rect()).center()
        self._burst = 1.0
        self._ripples.append(_Ripple(center, self._now()))
        self._start()

    def _start(self) -> None:
        self._last = self._now()
        self._overlay.setGeometry(self._button.rect())
        self._overlay.show()
        self._overlay.raise_()
        if not self._timer.isActive():
            self._timer.start()
        self._tick()

    # -- events ------------------------------------------------------------
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        etype = event.type()
        if etype == QEvent.Type.Enter:
            self.set_hovered(True)
        elif etype in (QEvent.Type.Leave, QEvent.Type.Hide):
            self.set_hovered(False)
        elif etype == QEvent.Type.EnabledChange and not self._button.isEnabled():
            self.set_hovered(False)
        elif etype == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.trigger_click(event.position())
        elif etype == QEvent.Type.Resize:
            self._overlay.setGeometry(self._button.rect())
        return False

    # -- animation ---------------------------------------------------------
    def _tick(self) -> None:
        if not shiboken6.isValid(self._button):
            self._timer.stop()
            return

        now = self._now()
        dt = max(0.0, min(0.05, now - self._last))
        self._last = now

        target = 1.0 if self._hovered else 0.0
        self._hover = _approach(self._hover, target, 4.0 if self._hovered else 2.5, dt)
        self._burst = max(0.0, self._burst - dt * 1.8)

        if self._sweep >= 0.0:
            self._sweep += dt / SWEEP_SECONDS
            if self._sweep > 1.0:
                self._sweep = -1.0
        if self._hovered and self._sweep < 0.0 and now >= self._next_sweep:
            self._sweep = 0.0
            self._next_sweep = now + SWEEP_PERIOD

        self._ripples = [r for r in self._ripples if now - r.started < RIPPLE_SECONDS]

        self._update_glow()
        self._overlay.update()

        idle = (
            not self._hovered
            and self._hover <= 0.0
            and self._burst <= 0.0
            and self._sweep < 0.0
            and not self._ripples
        )
        if idle:
            self._timer.stop()
            self._remove_effect()
            self._overlay.hide()

    def _update_glow(self) -> None:
        level = max(self._hover, self._burst)
        if level <= 0.001:
            self._remove_effect()
            return

        if self._effect is None:
            if self._button.graphicsEffect() is not None:
                return  # Respect effects set by other code
            effect = QGraphicsDropShadowEffect(self._button)
            effect.setOffset(0, 0)
            self._button.setGraphicsEffect(effect)
            self._effect = effect

        color = _rainbow(0.0, 0.8, 1.0, min(1.0, 0.9 * self._hover + self._burst))
        if self._burst > 0.0:
            color = _mix(color, QColor(255, 255, 255, 255), self._burst * 0.6)
        self._effect.setColor(color)
        self._effect.setBlurRadius(6.0 + 24.0 * self._hover + 38.0 * self._burst)

    def _remove_effect(self) -> None:
        if self._effect is None:
            return
        if shiboken6.isValid(self._effect) and shiboken6.isValid(self._button):
            if self._button.graphicsEffect() is not None:
                self._button.setGraphicsEffect(None)  # Qt deletes the effect
        self._effect = None

    # -- painting ----------------------------------------------------------
    def paint_overlay(self, painter: QPainter, rect: QRectF) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = 4.0 if self._button.objectName() == "ReportButton" else 6.0
        inner = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(inner, radius, radius)
        painter.setClipPath(path)

        hover = self._hover
        if hover > 0.0:
            # Glossy top-half highlight
            gloss = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            gloss.setColorAt(0.0, QColor(255, 255, 255, int(75 * hover)))
            gloss.setColorAt(0.48, QColor(255, 255, 255, int(14 * hover)))
            gloss.setColorAt(0.5, QColor(255, 255, 255, 0))
            gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, gloss)

            # Animated rainbow rim
            rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
            rim.setColorAt(0.0, _rainbow(0.0, 0.7, 1.0, hover))
            rim.setColorAt(0.5, _rainbow(0.33, 0.7, 1.0, hover))
            rim.setColorAt(1.0, _rainbow(0.66, 0.7, 1.0, hover))
            painter.setPen(QPen(rim, 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        # Diagonal shine sweep
        if self._sweep >= 0.0:
            band = max(26.0, rect.height() * 1.3)
            cx = -band + (rect.width() + 2.0 * band) * _ease_in_out(self._sweep)
            shine = QLinearGradient(QPointF(cx - band / 2.0, rect.top()), QPointF(cx + band / 2.0, rect.bottom()))
            shine.setColorAt(0.0, QColor(255, 255, 255, 0))
            shine.setColorAt(0.45, QColor(255, 255, 255, int(40 * max(hover, 0.4))))
            shine.setColorAt(0.5, QColor(255, 255, 255, int(150 * max(hover, 0.4))))
            shine.setColorAt(0.55, QColor(255, 255, 255, int(40 * max(hover, 0.4))))
            shine.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, shine)

        # Click flash + ripples
        if self._burst > 0.0:
            painter.fillRect(rect, QColor(255, 255, 255, int(70 * self._burst * self._burst)))
        if self._ripples:
            max_radius = (rect.width() ** 2 + rect.height() ** 2) ** 0.5
            _paint_ripples(painter, self._ripples, self._now(), max_radius)


class _ButtonFxManager(QObject):
    """Application-wide event filter that attaches ButtonFx to every QPushButton on first hover."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        if event.type() == QEvent.Type.Enter and isinstance(obj, QPushButton):
            if not obj.property(FX_PROPERTY):
                fx = ButtonFx(obj)
                fx.set_hovered(True)
        return False


_manager: _ButtonFxManager | None = None


def install_button_fx(app: QApplication | None = None) -> QObject:
    """Enables glow/shine/ripple effects for every QPushButton in the application (idempotent)."""
    global _manager
    app = app or QApplication.instance()
    if app is None:
        raise RuntimeError("install_button_fx() requires an existing QApplication")
    if _manager is None or not shiboken6.isValid(_manager):
        _manager = _ButtonFxManager(app)
        app.installEventFilter(_manager)
    return _manager


# ---------------------------------------------------------------------------
# Lists & tables
# ---------------------------------------------------------------------------
class GlowItemDelegate(QStyledItemDelegate):
    """Paints the hovered row of a list/table as a glowing gradient button with click ripples."""

    def __init__(self, view: QAbstractItemView) -> None:
        super().__init__(view)
        self._view = view
        self._hover_row = -1
        self._levels: dict[int, float] = {}
        self._ripples: list[_Ripple] = []

        self._clock = QElapsedTimer()
        self._clock.start()
        self._last = self._now()

        self._timer = QTimer(self)
        self._timer.setInterval(LIST_FRAME_MS)
        self._timer.timeout.connect(self._tick)

        view.setMouseTracking(True)
        view.viewport().setMouseTracking(True)
        view.viewport().installEventFilter(self)
        view.setItemDelegate(self)

    # -- state -------------------------------------------------------------
    def _now(self) -> float:
        return self._clock.elapsed() / 1000.0

    @property
    def hover_row(self) -> int:
        return self._hover_row

    def row_level(self, row: int) -> float:
        return self._levels.get(row, 0.0)

    def set_hover_row(self, row: int) -> None:
        if row == self._hover_row:
            return
        self._hover_row = row
        self._start()

    def trigger_click(self, row: int, pos: QPointF) -> None:
        if row < 0:
            return
        self._ripples.append(_Ripple(QPointF(pos), self._now(), row))
        self._start()

    def _row_at(self, pos: QPoint) -> int:
        index = self._view.indexAt(pos)
        return index.row() if index.isValid() else -1

    def _start(self) -> None:
        self._last = self._now()
        if not self._timer.isActive():
            self._timer.start()
        self._tick()

    # -- events ------------------------------------------------------------
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        etype = event.type()
        if etype == QEvent.Type.MouseMove:
            self.set_hover_row(self._row_at(event.position().toPoint()))
        elif etype in (QEvent.Type.Leave, QEvent.Type.Hide):
            self.set_hover_row(-1)
        elif etype == QEvent.Type.MouseButtonPress:
            pos = event.position()
            self.trigger_click(self._row_at(pos.toPoint()), pos)
        elif etype == QEvent.Type.Wheel:
            QTimer.singleShot(0, self._refresh_hover_from_cursor)
        return False

    def _refresh_hover_from_cursor(self) -> None:
        if not shiboken6.isValid(self._view):
            return
        viewport = self._view.viewport()
        pos = viewport.mapFromGlobal(QCursor.pos())
        self.set_hover_row(self._row_at(pos) if viewport.rect().contains(pos) else -1)

    # -- animation ---------------------------------------------------------
    def _tick(self) -> None:
        if not shiboken6.isValid(self._view):
            self._timer.stop()
            return

        now = self._now()
        dt = max(0.0, min(0.08, now - self._last))
        self._last = now

        if self._hover_row >= 0 and self._hover_row not in self._levels:
            self._levels[self._hover_row] = 0.0
        for row in list(self._levels):
            hovered = row == self._hover_row
            level = _approach(self._levels[row], 1.0 if hovered else 0.0, 6.0 if hovered else 3.0, dt)
            if level <= 0.0 and not hovered:
                del self._levels[row]
            else:
                self._levels[row] = level

        self._ripples = [r for r in self._ripples if now - r.started < RIPPLE_SECONDS]
        self._view.viewport().update()

        if not self._levels and not self._ripples and self._hover_row < 0:
            self._timer.stop()

    # -- painting ----------------------------------------------------------
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        row = index.row()
        level = self._levels.get(row, 0.0)
        ripples = [r for r in self._ripples if r.row == row]
        if level <= 0.001 and not ripples:
            super().paint(painter, option, index)
            return

        cell = QRectF(option.rect)
        if isinstance(self._view, QTableView):
            # Span the whole row so the gradient flows continuously across all cells
            last_col = max(0, self._view.model().columnCount() - 1)
            first = self._view.visualRect(index.siblingAtColumn(0))
            last = self._view.visualRect(index.siblingAtColumn(last_col))
            left, width = float(first.left()), float(last.right() - first.left() + 1)
        else:
            left, width = cell.left(), cell.width()
        row_rect = QRectF(left, cell.top(), width, cell.height()).adjusted(2.0, 1.5, -2.0, -1.5)

        path = QPainterPath()
        path.addRoundedRect(row_rect, 6.0, 6.0)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(cell)

        if level > 0.0:
            # Rainbow gradient fill spanning the whole row (continuous across table cells)
            fill = QLinearGradient(row_rect.topLeft(), row_rect.topRight())
            fill.setColorAt(0.0, _rainbow(0.00, 0.8, 0.95, 0.55 * level))
            fill.setColorAt(0.5, _rainbow(0.12, 0.8, 0.95, 0.42 * level))
            fill.setColorAt(1.0, _rainbow(0.24, 0.8, 0.95, 0.55 * level))
            painter.fillPath(path, fill)

            # Glossy highlight + inner glow, clipped inside the rounded row
            painter.setClipPath(path, Qt.ClipOperation.IntersectClip)
            gloss = QLinearGradient(row_rect.topLeft(), row_rect.bottomLeft())
            gloss.setColorAt(0.0, QColor(255, 255, 255, int(55 * level)))
            gloss.setColorAt(0.5, QColor(255, 255, 255, 0))
            painter.fillRect(row_rect, gloss)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for width, alpha in ((9.0, 0.10), (5.5, 0.18), (2.5, 0.35)):
                painter.setPen(QPen(_rainbow(0.06, 0.55, 1.0, alpha * level), width))
                painter.drawPath(path)

            # Bright animated rim
            painter.setClipRect(cell)
            rim = QLinearGradient(row_rect.topLeft(), row_rect.topRight())
            rim.setColorAt(0.0, _rainbow(0.00, 0.6, 1.0, 0.95 * level))
            rim.setColorAt(0.5, _rainbow(0.33, 0.6, 1.0, 0.95 * level))
            rim.setColorAt(1.0, _rainbow(0.66, 0.6, 1.0, 0.95 * level))
            painter.setPen(QPen(rim, 1.4))
            painter.drawPath(path)

        if ripples:
            painter.setClipRect(cell)
            painter.setClipPath(path, Qt.ClipOperation.IntersectClip)
            _paint_ripples(painter, ripples, self._now(), row_rect.width() * 0.75)

        painter.restore()

        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.StateFlag.State_MouseOver
        if level > 0.3:
            opt.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, opt, index)


def install_item_view_glow(view: QAbstractItemView) -> GlowItemDelegate:
    """Installs the glowing hover delegate on a single list/table (idempotent)."""
    existing = view.itemDelegate()
    if isinstance(existing, GlowItemDelegate):
        return existing
    return GlowItemDelegate(view)


def install_item_view_glow_recursive(root: QWidget) -> list[GlowItemDelegate]:
    """Installs the glow delegate on every list/table inside ``root`` (skips combo-box popups)."""
    delegates: list[GlowItemDelegate] = []
    for view in root.findChildren(QAbstractItemView):
        parent = view.parentWidget()
        inside_combo = False
        while parent is not None and parent is not root:
            if isinstance(parent, QComboBox):
                inside_combo = True
                break
            parent = parent.parentWidget()
        if inside_combo:
            continue
        delegates.append(install_item_view_glow(view))
    return delegates
