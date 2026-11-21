"""Dark mode stylesheet and color palette for PowerShellStore."""

DARK_THEME_QSS = """
/* Global Window and Base Styles */
QWidget {
    color: #f3f4f6;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

QMainWindow, QDialog, QMessageBox, QMenu {
    background-color: #0b1120;
}

QWidget#CentralBackdrop {
    background-color: transparent;
}

/* Splitter */
QSplitter {
    background-color: transparent;
}
QSplitter::handle {
    background-color: transparent;
    width: 3px;
}
QSplitter::handle:hover {
    background-color: rgba(96, 165, 250, 0.55);
}

/* Frosted Glass Panel Containers (underlit by ui/backdrop_fx.py) */
QFrame#SidebarFrame, QFrame#InspectorFrame, QFrame#CatalogFrame {
    background-color: rgba(15, 23, 42, 0.58);
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 10px;
}

QStatusBar {
    background-color: rgba(9, 14, 28, 0.78);
    color: #cbd5e1;
    border-top: 1px solid rgba(148, 163, 184, 0.18);
}

/* ScrollBars */
QScrollBar:vertical {
    background: rgba(10, 15, 30, 0.45);
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: rgba(71, 85, 105, 0.65);
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(100, 116, 139, 0.85);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: rgba(10, 15, 30, 0.45);
    height: 10px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: rgba(71, 85, 105, 0.65);
    min-width: 20px;
    border-radius: 5px;
}

/* Inputs & ComboBoxes */
QLineEdit, QSpinBox, QComboBox {
    background-color: rgba(10, 16, 32, 0.68);
    border: 1px solid rgba(148, 163, 184, 0.24);
    border-radius: 6px;
    padding: 6px 10px;
    color: #f9fafb;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #3b82f6;
}
QComboBox::drop-down {
    border: 0px;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #162036;
    border: 1px solid rgba(148, 163, 184, 0.28);
    selection-background-color: #2563eb;
    color: #f9fafb;
}

/* Push Buttons — colorful gradient on hover, inverted "pressed-in" gradient on click.
   The animated rainbow glow, shine sweep and click ripple are painted by ui/effects.py. */
QPushButton {
    background-color: #374151;
    color: #f9fafb;
    border: 1px solid #4b5563;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #6366f1, stop:0.35 #8b5cf6, stop:0.7 #ec4899, stop:1 #f59e0b);
    border: 1px solid #f0abfc;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: qlineargradient(x1:1, y1:1, x2:0, y2:0,
        stop:0 #4338ca, stop:0.5 #7e22ce, stop:1 #be185d);
    border: 1px solid #ffffff;
    padding-top: 8px;
    padding-bottom: 6px;
}
QPushButton:disabled {
    background-color: #1f2937;
    border: 1px solid #374151;
    color: #6b7280;
}

/* Primary Action Button (Blue -> Cyan -> Violet) */
QPushButton#PrimaryButton {
    background-color: #2563eb;
    border: 1px solid #1d4ed8;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#PrimaryButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #06b6d4, stop:0.45 #3b82f6, stop:1 #a855f7);
    border: 1px solid #a5f3fc;
}
QPushButton#PrimaryButton:pressed {
    background-color: qlineargradient(x1:1, y1:1, x2:0, y2:0,
        stop:0 #0e7490, stop:0.5 #1d4ed8, stop:1 #7e22ce);
    border: 1px solid #ffffff;
}

/* Success Button (Emerald -> Lime -> Teal) */
QPushButton#SuccessButton {
    background-color: #059669;
    border: 1px solid #047857;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#SuccessButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #10b981, stop:0.5 #84cc16, stop:1 #14b8a6);
    border: 1px solid #bbf7d0;
}
QPushButton#SuccessButton:pressed {
    background-color: qlineargradient(x1:1, y1:1, x2:0, y2:0,
        stop:0 #047857, stop:0.5 #4d7c0f, stop:1 #0f766e);
    border: 1px solid #ffffff;
}

/* Danger / Stop Button (Red -> Orange -> Magenta) */
QPushButton#DangerButton {
    background-color: #dc2626;
    border: 1px solid #b91c1c;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#DangerButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #ef4444, stop:0.5 #f97316, stop:1 #db2777);
    border: 1px solid #fecaca;
}
QPushButton#DangerButton:pressed {
    background-color: qlineargradient(x1:1, y1:1, x2:0, y2:0,
        stop:0 #991b1b, stop:0.5 #c2410c, stop:1 #9d174d);
    border: 1px solid #ffffff;
}
QPushButton#PrimaryButton:disabled, QPushButton#SuccessButton:disabled, QPushButton#DangerButton:disabled {
    background-color: #1f2937;
    border: 1px solid #374151;
    color: #6b7280;
}

/* Report Action Buttons (Dark Slate -> Aurora gradient on hover) */
QPushButton#ReportButton {
    background-color: #1f2937;
    border: 1px solid #374151;
    color: #e5e7eb;
    font-size: 11px;
    padding: 4px 10px;
    border-radius: 4px;
    font-weight: 500;
}
QPushButton#ReportButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #3b82f6, stop:0.5 #8b5cf6, stop:1 #ec4899);
    border: 1px solid #c4b5fd;
    color: #ffffff;
}
QPushButton#ReportButton:pressed {
    background-color: qlineargradient(x1:1, y1:0, x2:0, y2:0,
        stop:0 #1d4ed8, stop:0.5 #6d28d9, stop:1 #be185d);
    border: 1px solid #ffffff;
}
QPushButton#ReportButton:disabled {
    background-color: #111827;
    border-color: #1f2937;
    color: #4b5563;
}

/* Tables and Lists */
QTableWidget, QListWidget {
    background-color: rgba(9, 14, 28, 0.56);
    border: 1px solid rgba(148, 163, 184, 0.20);
    border-radius: 6px;
    gridline-color: rgba(51, 65, 85, 0.35);
    outline: none;
}
QTableWidget::item, QListWidget::item {
    padding: 8px;
    border-bottom: 1px solid rgba(51, 65, 85, 0.32);
}
QTableWidget::item:selected, QListWidget::item:selected {
    background-color: rgba(37, 99, 235, 0.55);
    color: #ffffff;
}
QHeaderView::section {
    background-color: rgba(20, 30, 54, 0.68);
    color: #cbd5e1;
    border: 0px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.22);
    padding: 8px;
    font-weight: 600;
}
QHeaderView::section:hover {
    background-color: rgba(37, 99, 235, 0.34);
    color: #ffffff;
}

/* Tab Widget */
QTabWidget::pane {
    border: 1px solid rgba(148, 163, 184, 0.22);
    background-color: rgba(11, 17, 34, 0.54);
    border-radius: 6px;
}
QTabBar::tab {
    background-color: rgba(22, 32, 56, 0.62);
    color: #9ca3af;
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: rgba(11, 17, 34, 0.78);
    color: #7dd3fc;
    border-bottom: 2px solid #38bdf8;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background-color: rgba(51, 65, 85, 0.68);
    color: #f3f4f6;
}

/* Code and Console Text Edit */
QPlainTextEdit#ConsoleView, QPlainTextEdit#CodePreview {
    background-color: rgba(3, 7, 18, 0.72);
    border: 1px solid rgba(148, 163, 184, 0.20);
    border-radius: 6px;
    color: #e5e7eb;
    font-family: Consolas, "Cascadia Code", "Courier New", monospace;
    font-size: 12px;
    line-height: 1.4;
}

/* Checkboxes */
QCheckBox {
    spacing: 8px;
    color: #f3f4f6;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #4b5563;
    background-color: #111827;
}
QCheckBox::indicator:checked {
    background-color: #2563eb;
    border: 1px solid #3b82f6;
}
QTableWidget::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #4b5563;
    background-color: #111827;
}
QTableWidget::indicator:hover {
    border: 1px solid #60a5fa;
}
QTableWidget::indicator:checked {
    background-color: #2563eb;
    border: 2px solid #93c5fd;
}

/* Badges and Labels */
QLabel#HeaderTitle {
    font-size: 18px;
    font-weight: 700;
    color: #ffffff;
}
QLabel#SectionTitle {
    font-size: 13px;
    font-weight: 600;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Opacity Slider */
QSlider::groove:horizontal {
    border: 1px solid #374151;
    height: 4px;
    background: #111827;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #2563eb;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #60a5fa;
    border: 1px solid #2563eb;
    width: 12px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 6px;
}
QSlider::handle:horizontal:hover {
    background: #93c5fd;
}

/* Fallback Native ToolTip Styling (primary animated tooltips rendered by ui/tooltip_fx.py) */
QToolTip {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #312e81, stop:0.45 #6d28d9, stop:0.8 #a21caf, stop:1 #0e7490);
    color: #f0f9ff;
    border: 1px solid #c084fc;
    border-radius: 8px;
    padding: 6px 10px;
    font-weight: 600;
}
"""

