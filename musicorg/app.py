"""QApplication bootstrap."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from musicorg.config.settings import AppSettings
from musicorg.runtime_paths import asset_path, builtin_themes_root, is_frozen, package_root
from musicorg.ui.main_window import MainWindow
from musicorg.ui.themes.registry import ThemeRegistry
from musicorg.ui.themes.service import ThemeService


def _configure_startup_logger(settings: AppSettings) -> logging.Logger:
    logger = logging.getLogger("musicorg.startup")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    log_dir = settings.app_data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "startup.log",
        maxBytes=512_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def run_app() -> int:
    """Initialize and run the application."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("MusicOrg")
    app.setOrganizationName("MusicOrg")
    settings = AppSettings()
    logger = _configure_startup_logger(settings)
    logger.info("startup mode frozen=%s package_root=%s", is_frozen(), package_root())

    icon_ico = asset_path("musicorg.ico")
    icon_png = asset_path("musicorg.png")
    icon_path = icon_ico if icon_ico.exists() else icon_png
    if not icon_path.exists():
        logger.warning("window icon not found: %s or %s", icon_ico, icon_png)
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    builtin_themes = builtin_themes_root()
    if not builtin_themes.exists():
        logger.warning("builtin theme root missing at %s", builtin_themes)

    theme_registry = ThemeRegistry(builtin_root=builtin_themes, user_root=settings.themes_dir)
    theme_service = ThemeService(app, settings, theme_registry)
    theme_service.reload_themes()
    errors = theme_registry.load_errors()
    if errors:
        logger.warning("theme load warnings: %s", " | ".join(errors[:6]))
    theme_service.apply_startup_theme()

    # Create and show main window
    window = MainWindow(settings, theme_service=theme_service)
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()

    exit_code = app.exec()
    return exit_code
