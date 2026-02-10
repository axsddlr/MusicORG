"""QApplication bootstrap, init beets config + library."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from musicorg.config.settings import AppSettings
from musicorg.core.beets_config import BeetsConfigManager
from musicorg.core.library import LibraryManager
from musicorg.ui.main_window import MainWindow
from musicorg.ui.theme import APP_STYLESHEET


def run_app() -> int:
    """Initialize and run the application."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    app.setApplicationName("MusicOrg")
    app.setOrganizationName("MusicOrg")
    icon_ico = Path(__file__).resolve().parent / "ui" / "assets" / "musicorg.ico"
    icon_png = Path(__file__).resolve().parent / "ui" / "assets" / "musicorg.png"
    icon_path = icon_ico if icon_ico.exists() else icon_png
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Initialize settings
    settings = AppSettings()

    # Initialize beets configuration
    beets_config = BeetsConfigManager(settings)
    try:
        beets_config.load()
    except Exception:
        pass  # App works without beets config for basic tag editing

    # Initialize library manager
    library = LibraryManager(settings)

    # Create and show main window
    window = MainWindow(settings)
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()

    exit_code = app.exec()

    # Cleanup
    library.close()
    return exit_code
