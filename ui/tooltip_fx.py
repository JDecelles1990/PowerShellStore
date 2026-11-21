"""Animated dynamic-rainbow tooltip with shining colorful background and smooth transitions.

Provides ``RainbowTooltip``, ``_TooltipFxManager``, and ``install_tooltip_fx(app)``:
- Intercepts Qt ``QEvent.Type.ToolTip`` events application-wide (widgets, ``QTabBar`` tabs,
  ``QHeaderView`` column headers, and item-view cells) without altering any button widgets or styles.
- Renders dynamic animated rainbow text (HiDPI offscreen ``SourceIn`` gradient mask + crisp dark
  drop-shadow for effortless readability).
- Paints a luminous, shifting colorful aurora background with glossy specular sheen, drifting
  color blooms, twinkling sparkle glints, periodic diagonal shine sweep, animated rainbow neon
  border rim, and soft breathing outer halo.
- Smoothly fades/slides/scales in on appear, glides on target switches, fades out on leave/click,
  and completely stops its timer when hidden (zero idle CPU).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import shiboken6
from PySide6.QtCore import QElapsedTimer, QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QHelpEvent,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QTabBar,
    QToolTip,
    QWidget,
)

TOOLTIP_FRAME_MS = 16       # ~60 fps while visible or transitioning
TEXT_RAINBOW_SPEED = 0.34   # rainbow cycles per second flowing across text
BG_DRIFT_SPEED = 0.14       # colorful aurora hue drift cycles per second
RIM_SPEED = 0.24            # rainbow border cycle speed
SWEEP_SECONDS = 0.72        # duration of a single diagonal shine sweep
SWEEP_PERIOD = 2.2          # seconds between shine sweeps while hovering
SHOW_DURATION = 0.22        # fade/slide/scale-in transition duration
HIDE_DURATION = 0.16        # fade/slide-out transition duration

GLOW_PAD = 18               # transparent outer margin around card for neon halo
CARD_RADIUS = 10.0
TEXT_PAD_X = 15
TEXT_PAD_Y = 9
MAX_TEXT_WIDTH = 340
CURSOR_OFFSET_X = 14
CURSOR_OFFSET_Y = 20
SLIDE_IN_PX = 8.0
SLIDE_OUT_PX = 4.0


# ---------------------------------------------------------------------------
# Easing & Color Helpers
# ---------------------------------------------------------------------------
def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _ease_out_cubic(t: float) -> float:
    t = _clamp(t)
    return 1.0 - (1.0 - t) ** 3


def _ease_in_out(t: float) -> float:
    t = _clamp(t)
    return t * t * (3.0 - 2.0 * t)


def _hsv_color(hue: float, sat: float, val: float, alpha: float = 1.0) -> QColor:
    return QColor.fromHsvF(hue % 1.0, _clamp(sat), _clamp(val), _clamp(alpha))


@dataclass(frozen=True)
class _SparkleSpec:
    nx: float      # normalized x position within card (0..1)
    ny: float      # normalized y position within card (0..1)
    phase: float   # phase offset in radians
    speed: float   # twinkle speed
    size: float    # star radius in px


_SPARKLES: tuple[_SparkleSpec, ...] = (
    _SparkleSpec(0.11, 0.20, 0.2, 3.4, 4.2),
    _SparkleSpec(0.37, 0.16, 1.9, 2.9, 3.4),
    _SparkleSpec(0.73, 0.22, 3.7, 3.8, 4.5),
    _SparkleSpec(0.91, 0.30, 5.1, 3.1, 3.6),
    _SparkleSpec(0.84, 0.80, 2.5, 2.7, 3.8),
    _SparkleSpec(0.22, 0.84, 4.4, 3.2, 3.3),
)


# ---------------------------------------------------------------------------
# Animated Rainbow Tooltip Popup Widget
# ---------------------------------------------------------------------------
class RainbowTooltip(QWidget):
    """Frameless translucent tooltip with dynamic rainbow text and shining colorful backdrop."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("RainbowTooltip")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        font = QFont("Segoe UI", 9)
        font.setWeight(QFont.Weight.DemiBold)
        self.setFont(font)

        self._text: str = ""
        self._state: str = "hidden"   # "hidden" | "showing" | "visible" | "hiding"
        self._progress: float = 0.0   # 0..1 visibility transition progress
        self._sweep: float = -1.0     # <0 inactive, 0..1 diagonal shine progress
        self._next_sweep: float = 0.0
        self._anchor_pos: QPoint = QPoint(0, 0)
        self._text_rect_size = QRect(0, 0, 120, 20)

        self._clock = QElapsedTimer()
        self._clock.start()
        self._last: float = self._now()

        self._timer = QTimer(self)
        self._timer.setInterval(TOOLTIP_FRAME_MS)
        self._timer.timeout.connect(self._tick)

    # -- inspection properties (also handy for unit tests) -----------------
    def _now(self) -> float:
        return self._clock.elapsed() / 1000.0

    @property
    def is_active(self) -> bool:
        return self._timer.isActive()

    @property
    def transition_progress(self) -> float:
        return self._progress

    @property
    def state(self) -> str:
        return self._state

    @property
    def text(self) -> str:
        return self._text

    # -- lifecycle ---------------------------------------------------------
    def show_tooltip(self, text: str, global_pos: QPoint) -> None:
        clean = text.strip()
        if not clean:
            self.hide_tooltip()
            return

        was_visible = self._state in ("showing", "visible")
        text_changed = clean != self._text
        self._text = clean
        self._resize_to_text()

        target_pos = self._compute_clamped_position(global_pos)
        self._anchor_pos = target_pos

        now = self._now()
        if not was_visible or text_changed:
            # Launch an immediate shine sweep on appear or content switch
            self._sweep = 0.0
            self._next_sweep = now + SWEEP_PERIOD

        self._state = "showing"
        self._last = now
        self._apply_animated_geometry()

        if not self.isVisible():
            self.show()
        self.raise_()
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def hide_tooltip(self, immediate: bool = False) -> None:
        if immediate or self._state == "hidden" or self._progress <= 0.0:
            self._state = "hidden"
            self._progress = 0.0
            self._sweep = -1.0
            self._timer.stop()
            if self.isVisible():
                self.hide()
            return

        if self._state != "hiding":
            self._state = "hiding"
            self._last = self._now()
            if not self._timer.isActive():
                self._timer.start()

    def _resize_to_text(self) -> None:
        metrics = QFontMetricsF(self.font())
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap)
        bounds = metrics.boundingRect(QRectF(0, 0, MAX_TEXT_WIDTH, 1000), flags, self._text)
        text_w = max(24, int(math.ceil(bounds.width())) + 4)
        text_h = max(18, int(math.ceil(bounds.height())) + 2)
        self._text_rect_size = QRect(0, 0, text_w, text_h)

        card_w = text_w + TEXT_PAD_X * 2
        card_h = text_h + TEXT_PAD_Y * 2
        self.resize(card_w + GLOW_PAD * 2, card_h + GLOW_PAD * 2)

    def _compute_clamped_position(self, global_pos: QPoint) -> QPoint:
        x = global_pos.x() + CURSOR_OFFSET_X - GLOW_PAD
        y = global_pos.y() + CURSOR_OFFSET_Y - GLOW_PAD

        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            card_w = self.width() - GLOW_PAD * 2
            card_h = self.height() - GLOW_PAD * 2

            # Flip horizontally if overflowing right edge
            if x + GLOW_PAD + card_w > avail.right() - 6:
                x = global_pos.x() - card_w - 14 - GLOW_PAD
            # Flip above cursor if overflowing bottom edge
            if y + GLOW_PAD + card_h > avail.bottom() - 6:
                y = global_pos.y() - card_h - 14 - GLOW_PAD

            # Hard clamp within screen available bounds
            min_x = avail.left() - GLOW_PAD + 4
            max_x = avail.right() - self.width() + GLOW_PAD - 4
            min_y = avail.top() - GLOW_PAD + 4
            max_y = avail.bottom() - self.height() + GLOW_PAD - 4
            if max_x >= min_x:
                x = max(min_x, min(max_x, x))
            if max_y >= min_y:
                y = max(min_y, min(max_y, y))

        return QPoint(int(x), int(y))

    def _apply_animated_geometry(self) -> None:
        eased = _ease_out_cubic(self._progress)
        if self._state == "hiding":
            y_offset = -SLIDE_OUT_PX * (1.0 - eased)
        else:
            y_offset = SLIDE_IN_PX * (1.0 - eased)
        self.move(self._anchor_pos.x(), int(round(self._anchor_pos.y() + y_offset)))

    # -- animation loop ----------------------------------------------------
    def _tick(self) -> None:
        now = self._now()
        dt = max(0.0, min(0.05, now - self._last))
        self._last = now

        if self._state == "showing":
            self._progress = _clamp(self._progress + dt / SHOW_DURATION)
            if self._progress >= 1.0:
                self._progress = 1.0
                self._state = "visible"
            self._apply_animated_geometry()
        elif self._state == "hiding":
            self._progress = _clamp(self._progress - dt / HIDE_DURATION)
            self._apply_animated_geometry()
            if self._progress <= 0.0:
                self._progress = 0.0
                self._state = "hidden"
                self._sweep = -1.0
                self._timer.stop()
                if self.isVisible():
                    self.hide()
                return

        # Advance periodic diagonal shine sweep
        if self._sweep >= 0.0:
            self._sweep += dt / SWEEP_SECONDS
            if self._sweep > 1.0:
                self._sweep = -1.0
        elif self._state in ("showing", "visible") and now >= self._next_sweep:
            self._sweep = 0.0
            self._next_sweep = now + SWEEP_PERIOD

        self.update()

    # -- painting ----------------------------------------------------------
    def _build_rainbow_text_image(
        self,
        text_rect: QRectF,
        hue_phase: float,
        alpha: float,
    ) -> QImage:
        """Renders anti-aliased tooltip text filled with an animated rainbow linear gradient."""
        dpr = max(1.0, float(self.devicePixelRatioF()))
        img_w = max(1, int(math.ceil(text_rect.width() * dpr)))
        img_h = max(1, int(math.ceil(text_rect.height() * dpr)))

        img = QImage(img_w, img_h, QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.GlobalColor.transparent)

        local_rect = QRectF(0.0, 0.0, text_rect.width(), text_rect.height())
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap)

        p = QPainter(img)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            p.setFont(self.font())
            p.setPen(QColor(255, 255, 255, 255))
            p.drawText(local_rect, flags, self._text)

            # Fill rendered glyph pixels with a vivid, luminous flowing rainbow gradient
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            grad = QLinearGradient(local_rect.topLeft(), local_rect.topRight())
            stops = 7
            for i in range(stops):
                pos = i / (stops - 1)
                # Vivid high-luminance neon-pastel rainbow for unmistakable color & crisp legibility
                hue = (hue_phase + pos * 0.90) % 1.0
                grad.setColorAt(pos, _hsv_color(hue, sat=0.66, val=1.0, alpha=alpha))
            p.fillRect(local_rect, grad)
        finally:
            p.end()

        return img

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        alpha = _ease_out_cubic(self._progress)
        if alpha <= 0.001 or not self._text:
            return

        now = self._now()
        text_hue = (now * TEXT_RAINBOW_SPEED) % 1.0
        # Keep aurora backdrop oscillating strictly inside rich jewel tones (cyan/sapphire/violet/magenta)
        bg_wave = math.sin(now * BG_DRIFT_SPEED * 2.0 * math.pi)
        rim_hue = (now * RIM_SPEED) % 1.0
        pulse = 0.84 + 0.16 * math.sin(now * 3.0)

        card_rect = QRectF(
            float(GLOW_PAD),
            float(GLOW_PAD),
            max(1.0, float(self.width() - GLOW_PAD * 2)),
            max(1.0, float(self.height() - GLOW_PAD * 2)),
        )

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

            # Subtle scale pop transition around card center
            scale = 0.92 + 0.08 * alpha
            center = card_rect.center()
            painter.translate(center)
            painter.scale(scale, scale)
            painter.translate(-center)

            # 1. Silky-smooth breathing colorful outer glow halo (10 feathered layers, zero banding)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            halo_layers = 10
            for i in range(halo_layers):
                t = i / (halo_layers - 1)  # 0 = outermost, 1 = innermost
                expand = 11.5 * (1.0 - t) + 0.6
                pen_w = 2.6 + 1.8 * (1.0 - t)
                glow_a = (0.022 + 0.21 * (t ** 2.1)) * pulse * alpha
                glow_rect = card_rect.adjusted(-expand, -expand, expand, expand)
                glow_path = QPainterPath()
                glow_path.addRoundedRect(
                    glow_rect, CARD_RADIUS + expand * 0.45, CARD_RADIUS + expand * 0.45
                )
                halo_grad = QLinearGradient(glow_rect.topLeft(), glow_rect.bottomRight())
                halo_grad.setColorAt(0.00, _hsv_color(rim_hue + 0.00, 0.88, 1.0, glow_a))
                halo_grad.setColorAt(0.35, _hsv_color(rim_hue + 0.28, 0.88, 1.0, glow_a))
                halo_grad.setColorAt(0.70, _hsv_color(rim_hue + 0.58, 0.88, 1.0, glow_a))
                halo_grad.setColorAt(1.00, _hsv_color(rim_hue + 0.86, 0.88, 1.0, glow_a))
                painter.setPen(QPen(halo_grad, pen_w))
                painter.drawPath(glow_path)

            # 2. Colorful shining iridescent aurora background card
            card_path = QPainterPath()
            card_path.addRoundedRect(card_rect, CARD_RADIUS, CARD_RADIUS)

            painter.save()
            painter.setClipPath(card_path)

            # Curated jewel-tone prism gradient (electric sapphire -> neon violet -> vivid magenta -> aurora teal)
            bg_grad = QLinearGradient(card_rect.topLeft(), card_rect.bottomRight())
            bg_grad.setColorAt(0.00, _hsv_color(0.64 + 0.04 * bg_wave, 0.84, 0.48, 0.97 * alpha))
            bg_grad.setColorAt(0.35, _hsv_color(0.75 + 0.04 * bg_wave, 0.80, 0.54, 0.97 * alpha))
            bg_grad.setColorAt(0.70, _hsv_color(0.87 - 0.04 * bg_wave, 0.82, 0.50, 0.97 * alpha))
            bg_grad.setColorAt(1.00, _hsv_color(0.54 + 0.05 * bg_wave, 0.86, 0.46, 0.97 * alpha))
            painter.fillRect(card_rect, bg_grad)

            # Drifting luminous aurora color blooms (cyan-aqua & fuchsia-orchid — always vivid, never muddy)
            b1_x = card_rect.left() + card_rect.width() * (0.26 + 0.18 * math.sin(now * 1.4))
            b1_y = card_rect.top() + card_rect.height() * (0.34 + 0.20 * math.cos(now * 1.1))
            b1_r = max(card_rect.width() * 0.50, 46.0)
            bloom1 = QRadialGradient(QPointF(b1_x, b1_y), b1_r)
            bloom1.setColorAt(0.0, _hsv_color(0.53 + 0.05 * math.sin(now), 0.90, 1.0, 0.36 * alpha))
            bloom1.setColorAt(0.55, _hsv_color(0.62, 0.85, 0.95, 0.14 * alpha))
            bloom1.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(card_rect, bloom1)

            b2_x = card_rect.left() + card_rect.width() * (0.76 + 0.16 * math.cos(now * 1.25))
            b2_y = card_rect.top() + card_rect.height() * (0.68 + 0.18 * math.sin(now * 1.5))
            b2_r = max(card_rect.width() * 0.46, 42.0)
            bloom2 = QRadialGradient(QPointF(b2_x, b2_y), b2_r)
            bloom2.setColorAt(0.0, _hsv_color(0.86 + 0.05 * math.cos(now * 0.9), 0.88, 1.0, 0.34 * alpha))
            bloom2.setColorAt(0.60, _hsv_color(0.76, 0.82, 0.95, 0.14 * alpha))
            bloom2.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(card_rect, bloom2)

            # Glossy specular glass reflection on upper half
            gloss = QLinearGradient(card_rect.topLeft(), card_rect.bottomLeft())
            gloss.setColorAt(0.00, QColor(255, 255, 255, int(105 * alpha)))
            gloss.setColorAt(0.42, QColor(255, 255, 255, int(24 * alpha)))
            gloss.setColorAt(0.52, QColor(255, 255, 255, 0))
            gloss.setColorAt(1.00, QColor(255, 255, 255, 0))
            painter.fillRect(card_rect, gloss)

            # Periodic diagonal holographic shine sweep
            if self._sweep >= 0.0:
                band = max(36.0, card_rect.height() * 1.55)
                cx = card_rect.left() - band + (card_rect.width() + 2.0 * band) * _ease_in_out(self._sweep)
                shine = QLinearGradient(
                    QPointF(cx - band * 0.55, card_rect.top()),
                    QPointF(cx + band * 0.55, card_rect.bottom()),
                )
                shine.setColorAt(0.00, QColor(255, 255, 255, 0))
                shine.setColorAt(0.34, _hsv_color(0.55, 0.65, 1.0, 0.24 * alpha))
                shine.setColorAt(0.50, QColor(255, 255, 255, int(190 * alpha)))
                shine.setColorAt(0.66, _hsv_color(0.85, 0.65, 1.0, 0.24 * alpha))
                shine.setColorAt(1.00, QColor(255, 255, 255, 0))
                painter.fillRect(card_rect, shine)

            # Twinkling starlight shimmer glints
            for sp in _SPARKLES:
                twinkle = (0.5 + 0.5 * math.sin(now * sp.speed + sp.phase)) ** 2.4
                if twinkle < 0.08:
                    continue
                sx = card_rect.left() + card_rect.width() * sp.nx
                sy = card_rect.top() + card_rect.height() * sp.ny
                r = sp.size * (0.55 + 0.45 * twinkle)
                star_alpha = int(215 * twinkle * alpha)
                star_pen = QPen(QColor(255, 255, 255, star_alpha), 1.1)
                painter.setPen(star_pen)
                painter.drawLine(QPointF(sx - r, sy), QPointF(sx + r, sy))
                painter.drawLine(QPointF(sx, sy - r), QPointF(sx, sy + r))
                core_grad = QRadialGradient(QPointF(sx, sy), r * 1.1)
                core_grad.setColorAt(0.0, QColor(255, 255, 255, star_alpha))
                core_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(core_grad)
                painter.drawEllipse(QPointF(sx, sy), r * 0.9, r * 0.9)

            # Subtle inner dark-indigo contrast scrim so bright rainbow letters pop cleanly
            inner_scrim = QLinearGradient(card_rect.topLeft(), card_rect.bottomLeft())
            inner_scrim.setColorAt(0.0, QColor(10, 12, 34, int(42 * alpha)))
            inner_scrim.setColorAt(0.5, QColor(10, 12, 34, int(88 * alpha)))
            inner_scrim.setColorAt(1.0, QColor(10, 12, 34, int(58 * alpha)))
            painter.fillRect(card_rect, inner_scrim)

            painter.restore()

            # 3. Animated rainbow neon border rim
            rim_grad = QLinearGradient(card_rect.topLeft(), card_rect.bottomRight())
            rim_grad.setColorAt(0.00, _hsv_color(rim_hue + 0.00, 0.78, 1.0, 0.98 * alpha))
            rim_grad.setColorAt(0.33, _hsv_color(rim_hue + 0.33, 0.78, 1.0, 0.98 * alpha))
            rim_grad.setColorAt(0.66, _hsv_color(rim_hue + 0.66, 0.78, 1.0, 0.98 * alpha))
            rim_grad.setColorAt(1.00, _hsv_color(rim_hue + 0.99, 0.78, 1.0, 0.98 * alpha))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(rim_grad, 1.8))
            painter.drawPath(card_path)

            # 4. Crisp dark backing shadow + Dynamic Rainbow Gradient Text
            text_rect = card_rect.adjusted(
                float(TEXT_PAD_X),
                float(TEXT_PAD_Y),
                -float(TEXT_PAD_X),
                -float(TEXT_PAD_Y),
            )
            flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap)
            painter.setFont(self.font())

            # Soft multi-offset dark text shadow so rainbow letters stay razor sharp
            painter.setPen(QColor(4, 6, 18, int(235 * alpha)))
            painter.drawText(text_rect.translated(0.0, 1.3), flags, self._text)
            painter.setPen(QColor(4, 6, 18, int(150 * alpha)))
            painter.drawText(text_rect.translated(-0.6, 0.6), flags, self._text)
            painter.drawText(text_rect.translated(0.7, 0.7), flags, self._text)

            rainbow_img = self._build_rainbow_text_image(text_rect, text_hue, alpha)
            painter.drawImage(text_rect.topLeft(), rainbow_img)
        finally:
            painter.end()


# ---------------------------------------------------------------------------
# Application-Wide Tooltip Event Filter Manager
# ---------------------------------------------------------------------------
def resolve_tooltip_text(obj: QObject, pos: QPoint | None = None) -> str:
    """Extracts the effective tooltip text for widgets, tabs, table headers, and item views."""
    if not isinstance(obj, QWidget):
        return ""

    # 1. QTabBar tab-specific tooltips
    if isinstance(obj, QTabBar) and pos is not None:
        idx = obj.tabAt(pos)
        if idx >= 0:
            tab_tip = obj.tabToolTip(idx)
            if tab_tip:
                return tab_tip

    # 2. QHeaderView column/row header tooltips
    if isinstance(obj, QHeaderView) and pos is not None:
        section = obj.logicalIndexAt(pos)
        model = obj.model()
        if section >= 0 and model is not None:
            data = model.headerData(section, obj.orientation(), Qt.ItemDataRole.ToolTipRole)
            if isinstance(data, str) and data:
                return data

    # 3. Item-view viewport cell tooltips (QTableWidget, QListWidget, QTreeView)
    parent = obj.parentWidget()
    if isinstance(parent, QAbstractItemView) and obj is parent.viewport() and pos is not None:
        index = parent.indexAt(pos)
        if index.isValid():
            data = index.data(Qt.ItemDataRole.ToolTipRole)
            if isinstance(data, str) and data:
                return data

    # 4. Walk up parent chain for standard widget.toolTip() (handles child labels inside tooltip frames)
    widget: QWidget | None = obj
    while widget is not None:
        tip = widget.toolTip()
        if tip:
            return tip
        if widget.isWindow():
            break
        widget = widget.parentWidget()

    return ""


class _TooltipFxManager(QObject):
    """Application-wide event filter replacing static native tooltips with RainbowTooltip."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._popup = RainbowTooltip()
        self._target: QWidget | None = None
        self._target_subkey: object = None

    @property
    def popup(self) -> RainbowTooltip:
        return self._popup

    def _subkey_for(self, obj: QObject, pos: QPoint) -> object:
        if isinstance(obj, QTabBar):
            return ("tab", obj.tabAt(pos))
        if isinstance(obj, QHeaderView):
            return ("header", obj.logicalIndexAt(pos))
        if isinstance(obj, QWidget):
            parent = obj.parentWidget()
            if isinstance(parent, QAbstractItemView) and obj is parent.viewport():
                idx = parent.indexAt(pos)
                return ("cell", idx.row(), idx.column()) if idx.isValid() else None
        return None

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        if not shiboken6.isValid(self._popup):
            return False

        etype = event.type()

        if etype == QEvent.Type.ToolTip:
            if obj is self._popup or not isinstance(obj, QWidget):
                return False
            if not isinstance(event, QHelpEvent):
                return False

            text = resolve_tooltip_text(obj, event.pos())
            if text:
                QToolTip.hideText()
                self._target = obj
                self._target_subkey = self._subkey_for(obj, event.pos())
                self._popup.show_tooltip(text, event.globalPos())
                event.accept()
                return True

            self._target = None
            self._target_subkey = None
            self._popup.hide_tooltip()
            return False

        if etype == QEvent.Type.MouseMove and self._target is obj and self._popup.state in ("showing", "visible"):
            if self._target_subkey is not None and hasattr(event, "position"):
                new_key = self._subkey_for(obj, event.position().toPoint())
                if new_key != self._target_subkey:
                    self._target = None
                    self._target_subkey = None
                    self._popup.hide_tooltip()

        elif etype in (QEvent.Type.Leave, QEvent.Type.Hide, QEvent.Type.Destroy):
            if self._target is obj:
                self._target = None
                self._target_subkey = None
                self._popup.hide_tooltip()

        elif etype in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.Wheel,
            QEvent.Type.KeyPress,
            QEvent.Type.ApplicationDeactivate,
            QEvent.Type.WindowDeactivate,
        ):
            if self._popup.state in ("showing", "visible"):
                self._target = None
                self._target_subkey = None
                self._popup.hide_tooltip()

        return False


_tooltip_manager: _TooltipFxManager | None = None


def install_tooltip_fx(app: QApplication | None = None) -> _TooltipFxManager:
    """Installs the animated rainbow tooltip manager globally on QApplication (idempotent)."""
    global _tooltip_manager
    app = app or QApplication.instance()
    if app is None:
        raise RuntimeError("install_tooltip_fx() requires an existing QApplication")
    if _tooltip_manager is None or not shiboken6.isValid(_tooltip_manager):
        _tooltip_manager = _TooltipFxManager(app)
        app.installEventFilter(_tooltip_manager)
    return _tooltip_manager
