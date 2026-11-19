"""Dark mode stylesheet and color palette for PowerShellStore."""

DARK_THEME_QSS = """
/* Global Window and Base Styles */
QWidget {
    background-color: #111827;
    color: #f3f4f6;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

QMainWindow, QDialog {
    background-color: #111827;
}

/* Splitter */
QSplitter::handle {
    background-color: #1f2937;
    width: 2px;
}
QSplitter::handle:hover {
    background-color: #3b82f6;
}

/* Sidebar and Panel Containers */
QFrame#SidebarFrame, QFrame#InspectorFrame, QFrame#CatalogFrame {
    background-color: #1f2937;
    border: 1px solid #374151;
    border-radius: 8px;
}

/* ScrollBars */
QScrollBar:vertical {
    background: #111827;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #374151;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #4b5563;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: #111827;
    height: 10px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #374151;
    min-width: 20px;
    border-radius: 5px;
}

/* Inputs & ComboBoxes */
QLineEdit, QSpinBox, QComboBox {
    background-color: #111827;
    border: 1px solid #374151;
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
    background-color: #1f2937;
    border: 1px solid #374151;
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
    background-color: #111827;
    border: 1px solid #374151;
    border-radius: 6px;
    gridline-color: #1f2937;
    outline: none;
}
QTableWidget::item, QListWidget::item {
    padding: 8px;
    border-bottom: 1px solid #1f2937;
}
QTableWidget::item:selected, QListWidget::item:selected {
    background-color: #1e3a8a;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #1f2937;
    color: #9ca3af;
    border: 0px;
    border-bottom: 1px solid #374151;
    padding: 8px;
    font-weight: 600;
}
QHeaderView::section:hover {
    background-color: #374151;
    color: #f3f4f6;
}

/* Tab Widget */
QTabWidget::pane {
    border: 1px solid #374151;
    background-color: #111827;
    border-radius: 6px;
}
QTabBar::tab {
    background-color: #1f2937;
    color: #9ca3af;
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #111827;
    color: #60a5fa;
    border-bottom: 2px solid #3b82f6;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background-color: #374151;
    color: #f3f4f6;
}

/* Code and Console Text Edit */
QPlainTextEdit#ConsoleView, QPlainTextEdit#CodePreview {
    background-color: #030712;
    border: 1px solid #374151;
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
"""

