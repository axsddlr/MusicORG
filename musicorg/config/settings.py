"""Application settings via QSettings."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from PySide6.QtCore import QSettings


class AppSettings:
    """Wraps QSettings for persistent app configuration."""

    def __init__(self) -> None:
        self._qs = QSettings("MusicOrg", "MusicOrg")

    # -- directories --

    @property
    def source_dir(self) -> str:
        return self._qs.value("dirs/source", "", type=str)

    @source_dir.setter
    def source_dir(self, value: str) -> None:
        self._qs.setValue("dirs/source", value)

    @property
    def dest_dir(self) -> str:
        return self._qs.value("dirs/dest", "", type=str)

    @dest_dir.setter
    def dest_dir(self, value: str) -> None:
        self._qs.setValue("dirs/dest", value)

    # -- discogs --

    @property
    def discogs_token(self) -> str:
        return self._qs.value("discogs/token", "", type=str)

    @discogs_token.setter
    def discogs_token(self, value: str) -> None:
        self._qs.setValue("discogs/token", value)

    # -- path format --

    @property
    def path_format(self) -> str:
        default = "$albumartist/$album/$track $title"
        return self._qs.value("sync/path_format", default, type=str)

    @path_format.setter
    def path_format(self, value: str) -> None:
        self._qs.setValue("sync/path_format", value)

    # -- tag cache --

    @property
    def tag_cache_db_path(self) -> str:
        return str(self.app_data_dir / "tag_cache.db")

    # -- backdrop opacity --

    @property
    def backdrop_opacity(self) -> float:
        return self._qs.value("ui/backdrop_opacity", 0.07, type=float)

    @backdrop_opacity.setter
    def backdrop_opacity(self, value: float) -> None:
        self._qs.setValue("ui/backdrop_opacity", value)

    # -- theme --

    @property
    def theme_id(self) -> str:
        raw = self._qs.value("ui/theme_id", "musicorg-default", type=str)
        value = (raw or "").strip()
        return value or "musicorg-default"

    @theme_id.setter
    def theme_id(self, value: str) -> None:
        cleaned = (value or "").strip() or "musicorg-default"
        self._qs.setValue("ui/theme_id", cleaned)

    @property
    def theme_last_known_good_id(self) -> str:
        raw = self._qs.value("ui/theme_last_known_good_id", "musicorg-default", type=str)
        value = (raw or "").strip()
        return value or "musicorg-default"

    @theme_last_known_good_id.setter
    def theme_last_known_good_id(self, value: str) -> None:
        cleaned = (value or "").strip() or "musicorg-default"
        self._qs.setValue("ui/theme_last_known_good_id", cleaned)

    # -- album artwork selection mode --

    @property
    def album_artwork_selection_mode(self) -> str:
        raw = self._qs.value("ui/album_artwork_selection_mode", "single_click", type=str)
        mode = (raw or "").strip().lower()
        if mode in {"none", "single_click", "double_click"}:
            return mode
        return "single_click"

    @album_artwork_selection_mode.setter
    def album_artwork_selection_mode(self, value: str) -> None:
        mode = (value or "").strip().lower()
        if mode not in {"none", "single_click", "double_click"}:
            mode = "single_click"
        self._qs.setValue("ui/album_artwork_selection_mode", mode)

    # -- keybind overrides --

    @property
    def keybind_overrides(self) -> dict[str, str]:
        raw = self._qs.value("ui/keybind_overrides", {})
        if raw is None:
            return {}
        if isinstance(raw, Mapping):
            source_items = raw.items()
        else:
            return {}
        cleaned: dict[str, str] = {}
        for key, value in source_items:
            if isinstance(key, str) and isinstance(value, str):
                cleaned[key] = value
        return cleaned

    @keybind_overrides.setter
    def keybind_overrides(self, value: dict[str, str]) -> None:
        cleaned: dict[str, str] = {}
        for key, item in value.items():
            if isinstance(key, str) and isinstance(item, str):
                cleaned[key] = item
        self._qs.setValue("ui/keybind_overrides", cleaned)

    # -- window geometry --

    @property
    def window_geometry(self) -> bytes | None:
        return self._qs.value("ui/window_geometry")

    @window_geometry.setter
    def window_geometry(self, value: bytes) -> None:
        self._qs.setValue("ui/window_geometry", value)

    # -- helpers --

    @property
    def app_data_dir(self) -> Path:
        path = self._app_data_dir()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def themes_dir(self) -> Path:
        path = self.app_data_dir / "themes"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _app_data_dir() -> Path:
        import os
        base = Path(os.environ.get("APPDATA", Path.home() / ".config"))
        return base / "musicorg"
