"""PowerShellStore desktop application entry point."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from ui.launcher_view import LauncherView
from ui.styles import DARK_THEME_QSS

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("PowerShellStore")
    app.setOrganizationName("ITHelpdesk")
    # Keep application running in system tray when main window is hidden
    app.setQuitOnLastWindowClosed(False)

    # Set default modern font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Apply global Dark Mode QSS stylesheet
    app.setStyleSheet(DARK_THEME_QSS)

    # Detect startup / background launch arguments
    start_hidden = any(arg in sys.argv for arg in ("--startup", "--minimized", "--tray"))

    window = LauncherView()

    if not start_hidden:
        window.show()
    else:
        logging.info("PowerShellStore started in background/tray mode. Press Shift+F8 to display.")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
