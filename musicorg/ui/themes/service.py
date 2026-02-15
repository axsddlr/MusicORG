"""Runtime theme apply and persistence service."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from musicorg.ui.theme import build_stylesheet as build_default_stylesheet
from musicorg.ui.themes.compiler import compile_theme_stylesheet
from musicorg.ui.themes.constants import DEFAULT_THEME_ID
from musicorg.ui.themes.models import ThemeSummary
from musicorg.ui.themes.registry import ThemeRegistry


class ThemeService(QObject):
    """Apply themes to QApplication and persist selection."""

    theme_changed = Signal(str)

    def __init__(self, app: QApplication, settings, registry: ThemeRegistry) -> None:
        super().__init__()
        self._app = app
        self._settings = settings
        self._registry = registry
        self._active_theme_id = ""

    @property
    def active_theme_id(self) -> str:
        return self._active_theme_id

    @property
    def user_themes_dir(self) -> Path:
        return self._registry.user_root

    def set_user_themes_dir(self, path: Path) -> None:
        self._registry.set_user_root(path)

    def reload_themes(self) -> list[str]:
        self._registry.reload()
        return self._registry.load_errors()

    def available_themes(self) -> list[ThemeSummary]:
        return self._registry.list_themes()

    def apply_theme(self, theme_id: str, *, persist: bool = True) -> tuple[bool, str]:
        package = self._registry.get_theme(theme_id)
        if package is None:
            return False, f"Theme not found: {theme_id}"
        try:
            stylesheet = compile_theme_stylesheet(package)
        except Exception as exc:  # pragma: no cover - defensive boundary
            return False, f"Could not compile theme {theme_id}: {exc}"

        self._app.setStyleSheet(stylesheet)
        self._active_theme_id = theme_id
        if persist:
            self._settings.theme_id = theme_id
        self._settings.theme_last_known_good_id = theme_id
        self.theme_changed.emit(theme_id)
        return True, f"Applied theme: {package.manifest.name}"

    def apply_startup_theme(self) -> tuple[bool, str]:
        requested = self._settings.theme_id
        fallback = self._settings.theme_last_known_good_id
        candidates = [requested, fallback, DEFAULT_THEME_ID]
        seen: set[str] = set()

        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            ok, message = self.apply_theme(candidate, persist=True)
            if ok:
                return True, message
        self._app.setStyleSheet(build_default_stylesheet())
        self._active_theme_id = DEFAULT_THEME_ID
        self._settings.theme_id = DEFAULT_THEME_ID
        self._settings.theme_last_known_good_id = DEFAULT_THEME_ID
        self.theme_changed.emit(DEFAULT_THEME_ID)
        return False, "No valid theme package found; reverted to built-in default stylesheet."
