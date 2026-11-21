"""Dynamic app gradient backdrop & interactive mouse-hover frosted glass effect.

Provides a continuous midnight-cobalt / cyber-aurora animated gradient canvas behind
``LauncherView`` panes and interactive cursor-reactive frosted glass overlays on
``SidebarFrame``, ``CatalogFrame``, and ``InspectorFrame``.
"""

from __future__ import annotations

import math
import time

import shiboken6
from PySide6.QtCore import QElapsedTimer, QEvent, QObject, QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QFrame, QMainWindow, QWidget

BACKDROP_FX_PROPERTY = "_psstore_backdrop_fx"
BACKDROP_PANEL_NAMES: tuple[str, ...] = ("SidebarFrame", "CatalogFrame", "InspectorFrame")

BACKDROP_FRAME_MS = 30       # ~33 fps smooth ambient & hover transitions
AURORA_SPEED = 0.08          # ambient aurora orbit cycles per second
CURSOR_LERP_RATE = 14.0      # cursor tracking responsiveness (per second)
PANEL_HOVER_IN_RATE = 5.0    # panel glass hover fade-in rate
PANEL_HOVER_OUT_RATE = 3.0   # panel glass hover fade-out rate
GLASS_RADIUS = 10.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _approach(current: float, target: float, rate: float, dt: float) -> float:
    step = rate * dt
    if current < target:
        return min(target, current + step)
    return max(target, current - step)


def _hsv_color(hue: float, sat: float, val: float, alpha: float = 1.0) -> QColor:
    return QColor.fromHsvF(hue % 1.0, _clamp(sat), _clamp(val), _clamp(alpha))


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = _clamp(t)
    return QColor.fromRgbF(
        a.redF() + (b.redF() - a.redF()) * t,
        a.greenF() + (b.greenF() - a.greenF()) * t,
        a.blueF() + (b.blueF() - a.blueF()) * t,
        a.alphaF() + (b.alphaF() - a.alphaF()) * t,
    )


# ---------------------------------------------------------------------------
# Underlay Aurora Canvas & Per-Panel Glass Specular Overlays
# ---------------------------------------------------------------------------
class _BackdropCanvas(QWidget):
    """Animated gradient canvas lowered behind the central workstation panes."""

    def __init__(self, fx: "BackdropFx", parent: QWidget) -> None:
        super().__init__(parent)
        self._fx = fx
        self.setObjectName("BackdropCanvas")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setGeometry(parent.rect())
        self.lower()
        self.show()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        try:
            self._fx.paint_backdrop(painter, QRectF(self.rect()))
        finally:
            painter.end()


class _GlassPanelOverlay(QWidget):
    """Cursor-reactive specular highlight and illuminated glass border rim for a pane."""

    def __init__(self, fx: "BackdropFx", panel: QWidget) -> None:
        super().__init__(panel)
        self._fx = fx
        self._panel = panel
        self.setObjectName(f"{panel.objectName()}_GlassOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background: transparent; border: none;")
        self.setGeometry(panel.rect())
        self.raise_()
        self.show()

    @property
    def panel(self) -> QWidget:
        return self._panel

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        try:
            self._fx.paint_panel_overlay(painter, self._panel, QRectF(self.rect()))
        finally:
            painter.end()


# ---------------------------------------------------------------------------
# Main Backdrop & Frosted Glass Controller
# ---------------------------------------------------------------------------
class BackdropFx(QObject):
    """Manages the dynamic gradient backdrop and interactive glass hover effects."""

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self._window = window
        central = window.centralWidget()
        if central is None:
            raise RuntimeError("BackdropFx requires window.centralWidget() to exist")
        self._central = central

        # Enable hover delivery across the central canvas and glass panes even over child labels
        central.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        central.setMouseTracking(True)

        self._clock = QElapsedTimer()
        self._clock.start()
        self._last = self._now()

        self._cursor_active: bool = False
        self._target_cursor = QPointF(max(1.0, central.width()) * 0.5, max(1.0, central.height()) * 0.45)
        self._smooth_cursor = QPointF(self._target_cursor)
        self._cursor_presence: float = 0.0  # 0..1 smooth fade of cursor spotlight

        self._panels: dict[str, QWidget] = {}
        self._hover_levels: dict[str, float] = {}
        self._hovered_panel: str | None = None
        self._overlays: dict[str, _GlassPanelOverlay] = {}

        self._canvas = _BackdropCanvas(self, central)

        for name in BACKDROP_PANEL_NAMES:
            panel = window.findChild(QFrame, name)
            if panel is not None:
                panel.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
                panel.setMouseTracking(True)
                self._panels[name] = panel
                self._hover_levels[name] = 0.0
                overlay = _GlassPanelOverlay(self, panel)
                self._overlays[name] = overlay
                panel.installEventFilter(self)

        central.installEventFilter(self)
        window.installEventFilter(self)

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        self._timer = QTimer(self)
        self._timer.setInterval(BACKDROP_FRAME_MS)
        self._timer.timeout.connect(self._tick)

        window.setProperty(BACKDROP_FX_PROPERTY, self)
        if window.isVisible():
            self._start_timer()

    # -- inspection & test hooks -------------------------------------------
    def _now(self) -> float:
        return self._clock.elapsed() / 1000.0

    @property
    def canvas(self) -> _BackdropCanvas:
        return self._canvas

    @property
    def panel_overlays(self) -> dict[str, _GlassPanelOverlay]:
        return self._overlays

    @property
    def is_active(self) -> bool:
        return self._timer.isActive()

    @property
    def cursor_active(self) -> bool:
        return self._cursor_active

    @property
    def hovered_panel(self) -> str | None:
        return self._hovered_panel

    def panel_hover_level(self, name: str) -> float:
        return self._hover_levels.get(name, 0.0)

    def _start_timer(self) -> None:
        self._last = self._now()
        if not self._timer.isActive():
            self._timer.start()

    # -- cursor state ------------------------------------------------------
    def set_cursor_pos(self, pos: QPointF | QPoint) -> None:
        """Sets the target cursor position in centralWidget coordinates."""
        pt = QPointF(pos)
        was_active = self._cursor_active
        self._cursor_active = True
        self._target_cursor = pt
        if not was_active:
            self._smooth_cursor = QPointF(pt)

        # Determine which glass panel currently contains the cursor
        hovered: str | None = None
        for name, panel in self._panels.items():
            if not shiboken6.isValid(panel) or not panel.isVisibleTo(self._central):
                continue
            top_left = panel.mapTo(self._central, QPoint(0, 0))
            panel_rect = QRectF(float(top_left.x()), float(top_left.y()), float(panel.width()), float(panel.height()))
            if panel_rect.contains(pt):
                hovered = name
                break
        self._hovered_panel = hovered

        if self._window.isVisible():
            self._start_timer()

    def clear_cursor(self) -> None:
        """Clears active cursor spotlight and panel hover target so glow fades cleanly."""
        self._cursor_active = False
        self._hovered_panel = None

    # -- Qt event filter ---------------------------------------------------
    def _belongs_to_window(self, obj: QObject) -> bool:
        if obj is self._window or obj is self._central:
            return True
        if isinstance(obj, QWidget):
            if obj is self._canvas or obj in self._overlays.values():
                return False
            return obj.window() is self._window
        return False

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        if not shiboken6.isValid(self._window) or not shiboken6.isValid(self._central):
            self._timer.stop()
            return False

        etype = event.type()

        if obj is self._central and etype == QEvent.Type.Resize:
            self._canvas.setGeometry(self._central.rect())
            self._canvas.lower()
            return False

        if isinstance(obj, QWidget) and obj.objectName() in self._overlays:
            name = obj.objectName()
            overlay = self._overlays[name]
            if etype == QEvent.Type.Resize:
                overlay.setGeometry(obj.rect())
                overlay.raise_()
            elif etype in (QEvent.Type.Show, QEvent.Type.ChildAdded):
                overlay.setGeometry(obj.rect())
                overlay.raise_()

        if obj is self._window:
            if etype in (QEvent.Type.Show, QEvent.Type.WindowActivate):
                self._canvas.setGeometry(self._central.rect())
                self._canvas.lower()
                for overlay in self._overlays.values():
                    if shiboken6.isValid(overlay) and shiboken6.isValid(overlay.panel):
                        overlay.setGeometry(overlay.panel.rect())
                        overlay.raise_()
                self._start_timer()
            elif etype == QEvent.Type.Close:
                self._timer.stop()
            elif etype == QEvent.Type.Leave:
                self.clear_cursor()
            return False

        if etype in (QEvent.Type.HoverMove, QEvent.Type.MouseMove, QEvent.Type.Enter):
            if self._belongs_to_window(obj) and isinstance(obj, QWidget):
                if hasattr(event, "globalPosition"):
                    local_pos = self._central.mapFromGlobal(event.globalPosition().toPoint())
                elif hasattr(event, "position"):
                    global_pt = obj.mapToGlobal(event.position().toPoint())
                    local_pos = self._central.mapFromGlobal(global_pt)
                else:
                    return False

                if self._central.rect().contains(local_pos):
                    self.set_cursor_pos(local_pos)
                else:
                    self.clear_cursor()

        return False

    # -- animation loop ----------------------------------------------------
    def _tick(self) -> None:
        if not shiboken6.isValid(self._window) or not shiboken6.isValid(self._central):
            self._timer.stop()
            return

        now = self._now()
        dt = max(0.0, min(0.08, now - self._last))
        self._last = now

        # Smoothly glide spotlight toward cursor
        lerp_factor = min(1.0, CURSOR_LERP_RATE * dt) if dt > 0 else 1.0
        self._smooth_cursor = QPointF(
            self._smooth_cursor.x() + (self._target_cursor.x() - self._smooth_cursor.x()) * lerp_factor,
            self._smooth_cursor.y() + (self._target_cursor.y() - self._smooth_cursor.y()) * lerp_factor,
        )
        self._cursor_presence = _approach(
            self._cursor_presence,
            1.0 if self._cursor_active else 0.0,
            PANEL_HOVER_IN_RATE if self._cursor_active else PANEL_HOVER_OUT_RATE,
            dt,
        )

        # Smoothly ease hover level for each pane
        for name in self._hover_levels:
            target = 1.0 if (self._cursor_active and self._hovered_panel == name) else 0.0
            rate = PANEL_HOVER_IN_RATE if target > self._hover_levels[name] else PANEL_HOVER_OUT_RATE
            self._hover_levels[name] = _approach(self._hover_levels[name], target, rate, dt)

        # Keep underlay canvas & overlays aligned
        if self._canvas.geometry() != self._central.rect():
            self._canvas.setGeometry(self._central.rect())
            self._canvas.lower()

        self._canvas.update()
        for name, overlay in self._overlays.items():
            if shiboken6.isValid(overlay) and shiboken6.isValid(overlay.panel):
                if overlay.geometry() != overlay.panel.rect():
                    overlay.setGeometry(overlay.panel.rect())
                if overlay.panel.isVisibleTo(self._central):
                    overlay.update()

        # Pause animation timer completely if main window is hidden & hover animations settled
        all_idle = (
            not self._cursor_active
            and self._cursor_presence <= 0.0
            and all(lvl <= 0.0 for lvl in self._hover_levels.values())
        )
        if not self._window.isVisible() and all_idle:
            self._timer.stop()

    # -- painting ----------------------------------------------------------
    def paint_backdrop(self, painter: QPainter, rect: QRectF) -> None:
        if rect.width() <= 1.0 or rect.height() <= 1.0:
            return

        now = self._now()
        phase = now * AURORA_SPEED * 2.0 * math.pi

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Layer A: Dynamic diagonal Midnight-Sapphire & Cyber-Indigo base gradient
        shift_x = rect.width() * 0.08 * math.sin(phase * 0.7)
        shift_y = rect.height() * 0.08 * math.cos(phase * 0.6)
        base_grad = QLinearGradient(
            QPointF(rect.left() + shift_x, rect.top()),
            QPointF(rect.right() - shift_x, rect.bottom() + shift_y),
        )
        base_grad.setColorAt(0.00, _mix(QColor("#060b18"), QColor("#0a1430"), 0.5 + 0.5 * math.sin(phase * 0.5)))
        base_grad.setColorAt(0.35, _mix(QColor("#0d1b3e"), QColor("#11214a"), 0.5 + 0.5 * math.cos(phase * 0.6)))
        base_grad.setColorAt(0.72, _mix(QColor("#17133a"), QColor("#1f1645"), 0.5 + 0.5 * math.sin(phase * 0.8 + 1.0)))
        base_grad.setColorAt(1.00, _mix(QColor("#071c29"), QColor("#0b2738"), 0.5 + 0.5 * math.cos(phase * 0.4 + 2.0)))
        painter.fillRect(rect, base_grad)

        # Layer B: 4 Drifting Ambient Aurora Nebulas tuned to PowerShellStore dark cyber theme
        orbs = (
            # (cx_norm, cy_norm, rx, ry, radius_factor, primary, secondary)
            (0.18 + 0.09 * math.sin(phase * 0.8), 0.22 + 0.08 * math.cos(phase * 0.6),
             0.52, QColor(37, 99, 235, 92), QColor(6, 182, 212, 46)),
            (0.78 + 0.08 * math.cos(phase * 0.65), 0.24 + 0.10 * math.sin(phase * 0.75),
             0.54, QColor(124, 58, 237, 88), QColor(168, 85, 247, 42)),
            (0.46 + 0.12 * math.sin(phase * 0.55 + 1.6), 0.84 + 0.07 * math.cos(phase * 0.85),
             0.48, QColor(13, 148, 136, 78), QColor(16, 185, 129, 34)),
            (0.68 + 0.10 * math.cos(phase * 0.9 + 0.7), 0.62 + 0.09 * math.sin(phase * 0.7),
             0.42, QColor(219, 39, 119, 54), QColor(236, 72, 153, 22)),
        )
        max_dim = max(rect.width(), rect.height())
        for cx_n, cy_n, rad_scale, c_core, c_mid in orbs:
            center = QPointF(rect.left() + rect.width() * cx_n, rect.top() + rect.height() * cy_n)
            radius = max_dim * rad_scale
            orb_grad = QRadialGradient(center, radius)
            orb_grad.setColorAt(0.00, c_core)
            orb_grad.setColorAt(0.45, c_mid)
            orb_grad.setColorAt(1.00, QColor(0, 0, 0, 0))
            painter.fillRect(rect, orb_grad)

        # Layer C: Cursor-Tracking Interactive Aurora Spotlight behind all panes
        if self._cursor_presence > 0.001:
            p_alpha = self._cursor_presence
            spot_radius = 380.0
            spot = QRadialGradient(self._smooth_cursor, spot_radius)
            spot.setColorAt(0.00, QColor(56, 189, 248, int(62 * p_alpha)))
            spot.setColorAt(0.42, QColor(139, 92, 246, int(36 * p_alpha)))
            spot.setColorAt(0.74, QColor(236, 72, 153, int(16 * p_alpha)))
            spot.setColorAt(1.00, QColor(0, 0, 0, 0))
            painter.fillRect(rect, spot)

        # Layer D: Under-Panel Interactive Frosted Glass Refraction Glow
        for name, panel in self._panels.items():
            if not shiboken6.isValid(panel) or not panel.isVisibleTo(self._central):
                continue
            top_left = panel.mapTo(self._central, QPoint(0, 0))
            panel_rect = QRectF(
                float(top_left.x()),
                float(top_left.y()),
                float(panel.width()),
                float(panel.height()),
            )
            if not rect.intersects(panel_rect):
                continue

            panel_path = QPainterPath()
            panel_path.addRoundedRect(panel_rect, GLASS_RADIUS, GLASS_RADIUS)

            painter.save()
            painter.setClipPath(panel_path)

            # Subtle under-glass base depth tint
            painter.fillRect(panel_rect, QColor(15, 23, 42, 108))

            hover = self._hover_levels.get(name, 0.0)
            if self._cursor_presence > 0.001:
                refract_r = 280.0
                refract = QRadialGradient(self._smooth_cursor, refract_r)
                boost = (0.45 + 0.55 * hover) * self._cursor_presence
                refract.setColorAt(0.00, QColor(56, 189, 248, int(44 * boost)))
                refract.setColorAt(0.50, QColor(124, 58, 237, int(24 * boost)))
                refract.setColorAt(1.00, QColor(0, 0, 0, 0))
                painter.fillRect(panel_rect, refract)

            if hover > 0.001:
                sheen = QLinearGradient(panel_rect.topLeft(), panel_rect.bottomRight())
                sheen.setColorAt(0.00, QColor(125, 211, 252, int(22 * hover)))
                sheen.setColorAt(0.45, QColor(167, 139, 250, int(12 * hover)))
                sheen.setColorAt(1.00, QColor(20, 184, 166, int(16 * hover)))
                painter.fillRect(panel_rect, sheen)

            painter.restore()

        painter.restore()

    def paint_panel_overlay(self, painter: QPainter, panel: QWidget, rect: QRectF) -> None:
        if rect.width() <= 2.0 or rect.height() <= 2.0:
            return

        name = panel.objectName()
        hover = self._hover_levels.get(name, 0.0)
        local_cursor = QPointF(panel.mapFrom(self._central, self._smooth_cursor.toPoint()))
        # Retain subpixel smoothness for local spotlight mapping
        top_left_in_central = panel.mapTo(self._central, QPoint(0, 0))
        local_cursor = QPointF(
            self._smooth_cursor.x() - float(top_left_in_central.x()),
            self._smooth_cursor.y() - float(top_left_in_central.y()),
        )

        inner = rect.adjusted(0.6, 0.6, -0.6, -0.6)
        clip_path = QPainterPath()
        clip_path.addRoundedRect(inner, GLASS_RADIUS, GLASS_RADIUS)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipPath(clip_path)

        # 1. Top-edge frosted glass specular catch-light
        top_reflect = QLinearGradient(inner.topLeft(), QPointF(inner.left(), inner.top() + inner.height() * 0.45))
        top_reflect.setColorAt(0.0, QColor(255, 255, 255, int(18 + 20 * hover)))
        top_reflect.setColorAt(0.35, QColor(224, 242, 254, int(7 + 10 * hover)))
        top_reflect.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(inner, top_reflect)

        # 2. Interactive pearlescent mouse-hover glass surface spotlight
        if self._cursor_presence > 0.001 and (hover > 0.001 or inner.adjusted(-180, -180, 180, 180).contains(local_cursor)):
            surf_intensity = (0.35 + 0.65 * hover) * self._cursor_presence
            surf_grad = QRadialGradient(local_cursor, 260.0)
            surf_grad.setColorAt(0.00, QColor(186, 230, 253, int(30 * surf_intensity)))
            surf_grad.setColorAt(0.45, QColor(196, 181, 253, int(16 * surf_intensity)))
            surf_grad.setColorAt(1.00, QColor(255, 255, 255, 0))
            painter.fillRect(inner, surf_grad)

        painter.restore()

        # 3. Cursor-illuminated 3D specular glass border rim (Fluent reveal border)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Base crisp frosted border
        painter.setPen(QPen(QColor(148, 163, 184, int(52 + 26 * hover)), 1.2))
        painter.drawPath(clip_path)

        # Cursor-following luminous glass rim highlight
        if self._cursor_presence > 0.001:
            rim_strength = (0.55 + 0.45 * hover) * self._cursor_presence
            rim_grad = QRadialGradient(local_cursor, 260.0)
            rim_grad.setColorAt(0.00, QColor(125, 211, 252, int(235 * rim_strength)))
            rim_grad.setColorAt(0.45, QColor(196, 181, 253, int(145 * rim_strength)))
            rim_grad.setColorAt(0.78, QColor(249, 168, 212, int(55 * rim_strength)))
            rim_grad.setColorAt(1.00, QColor(255, 255, 255, 0))
            painter.setPen(QPen(rim_grad, 1.8))
            painter.drawPath(clip_path)

        painter.restore()


def install_backdrop_fx(window: QMainWindow) -> BackdropFx:
    """Installs the dynamic gradient backdrop and glass overlays on ``window`` (idempotent)."""
    existing = window.property(BACKDROP_FX_PROPERTY)
    if isinstance(existing, BackdropFx) and shiboken6.isValid(existing):
        return existing
    return BackdropFx(window)
