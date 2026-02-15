"""QApplication bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from musicorg.config.settings import AppSettings
from musicorg.ui.main_window import MainWindow
from musicorg.ui.themes.registry import ThemeRegistry
from musicorg.ui.themes.service import ThemeService


def run_app() -> int:
    """Initialize and run the application."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("MusicOrg")
    app.setOrganizationName("MusicOrg")
    icon_ico = Path(__file__).resolve().parent / "ui" / "assets" / "musicorg.ico"
    icon_png = Path(__file__).resolve().parent / "ui" / "assets" / "musicorg.png"
    icon_path = icon_ico if icon_ico.exists() else icon_png
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Initialize settings
    settings = AppSettings()
    builtin_themes = Path(__file__).resolve().parent / "ui" / "themes" / "builtin"
    theme_registry = ThemeRegistry(builtin_root=builtin_themes, user_root=settings.themes_dir)
    theme_service = ThemeService(app, settings, theme_registry)
    theme_service.reload_themes()
    theme_service.apply_startup_theme()

    # Create and show main window
    window = MainWindow(settings, theme_service=theme_service)
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()

    exit_code = app.exec()
    return exit_code
