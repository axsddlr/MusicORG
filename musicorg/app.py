"""QApplication bootstrap, init beets config + library."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from musicorg.config.settings import AppSettings
from musicorg.core.beets_config import BeetsConfigManager
from musicorg.core.library import LibraryManager
from musicorg.ui.main_window import MainWindow


def run_app() -> int:
    """Initialize and run the application."""
    app = QApplication(sys.argv)
    app.setApplicationName("MusicOrg")
    app.setOrganizationName("MusicOrg")

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
    window.show()

    exit_code = app.exec()

    # Cleanup
    library.close()
    return exit_code
