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

    # Set default modern font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Apply global Dark Mode QSS stylesheet
    app.setStyleSheet(DARK_THEME_QSS)

    window = LauncherView()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
