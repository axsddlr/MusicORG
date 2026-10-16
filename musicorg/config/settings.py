"""Application settings via QSettings."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from PySide6.QtCore import QSettings


_VALID_PATH_VARS = {"albumartist", "artist", "album", "disc", "disc0", "disc-", "track", "title", "year"}
_PATH_VAR_RE = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_-]*)")


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

    # -- spotify --

    @property
    def spotify_client_id(self) -> str:
        return self._qs.value("spotify/client_id", "", type=str)

    @spotify_client_id.setter
    def spotify_client_id(self, value: str) -> None:
        self._qs.setValue("spotify/client_id", value)

    @property
    def spotify_client_secret(self) -> str:
        return self._qs.value("spotify/client_secret", "", type=str)

    @spotify_client_secret.setter
    def spotify_client_secret(self, value: str) -> None:
        self._qs.setValue("spotify/client_secret", value)

    # -- path format --

    @property
    def path_format(self) -> str:
        default = "$albumartist/$album/$track $title"
        return self._qs.value("sync/path_format", default, type=str)

    @path_format.setter
    def path_format(self, value: str) -> None:
        invalid = set(_PATH_VAR_RE.findall(value)) - _VALID_PATH_VARS
        if invalid:
            raise ValueError(f"Unknown path format variables: {', '.join(sorted(invalid))}")
        self._qs.setValue("sync/path_format", value)

    # -- tag cache --

    @property
    def tag_cache_db_path(self) -> str:
        return str(self.app_data_dir / "tag_cache.db")

    @property
    def track_identity_db_path(self) -> str:
        return str(self.app_data_dir / "track_identity.db")

    @property
    def library_db_path(self) -> str:
        return str(self.app_data_dir / "library.db")

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

    @property
    def theme_custom_dir(self) -> str:
        raw = self._qs.value("ui/theme_custom_dir", "", type=str)
        return (raw or "").strip()

    @theme_custom_dir.setter
    def theme_custom_dir(self, value: str) -> None:
        cleaned = (value or "").strip()
        self._qs.setValue("ui/theme_custom_dir", cleaned)

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

    # -- plugins --

    @property
    def plugins_safe_mode(self) -> bool:
        return self._qs.value("plugins/safe_mode", False, type=bool)

    @plugins_safe_mode.setter
    def plugins_safe_mode(self, value: bool) -> None:
        self._qs.setValue("plugins/safe_mode", bool(value))

    @property
    def plugins_dir(self) -> str:
        raw = self._qs.value("plugins/dir", "", type=str)
        return (raw or "").strip()

    @plugins_dir.setter
    def plugins_dir(self, value: str) -> None:
        self._qs.setValue("plugins/dir", (value or "").strip())

    @property
    def plugin_enabled_map(self) -> dict[str, bool]:
        raw = self._qs.value("plugins/enabled", {})
        if not isinstance(raw, Mapping):
            return {}
        cleaned: dict[str, bool] = {}
        for key, value in raw.items():
            if isinstance(key, str):
                cleaned[key] = bool(value)
        return cleaned

    @plugin_enabled_map.setter
    def plugin_enabled_map(self, value: Mapping[str, object]) -> None:
        cleaned: dict[str, bool] = {}
        for key, item in value.items():
            if isinstance(key, str):
                cleaned[key] = bool(item)
        self._qs.setValue("plugins/enabled", cleaned)

    @property
    def plugin_crash_counters(self) -> dict[str, int]:
        raw = self._qs.value("plugins/crash_counters", {})
        if not isinstance(raw, Mapping):
            return {}
        cleaned: dict[str, int] = {}
        for key, value in raw.items():
            if not isinstance(key, str):
                continue
            try:
                cleaned[key] = max(0, int(value))
            except (TypeError, ValueError):
                cleaned[key] = 0
        return cleaned

    @plugin_crash_counters.setter
    def plugin_crash_counters(self, value: Mapping[str, object]) -> None:
        cleaned: dict[str, int] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            try:
                cleaned[key] = max(0, int(item))
            except (TypeError, ValueError):
                cleaned[key] = 0
        self._qs.setValue("plugins/crash_counters", cleaned)

    @property
    def plugin_startup_timeout_ms(self) -> int:
        value = self._qs.value("plugins/startup_timeout_ms", 4000, type=int)
        return max(250, int(value))

    @plugin_startup_timeout_ms.setter
    def plugin_startup_timeout_ms(self, value: int) -> None:
        self._qs.setValue("plugins/startup_timeout_ms", max(250, int(value)))

    def plugin_get_setting(self, plugin_id: str, key: str, default: object | None = None) -> object:
        safe_plugin_id = self._sanitize_plugin_id(plugin_id)
        safe_key = self._sanitize_plugin_key(key)
        return self._qs.value(f"plugins/data/{safe_plugin_id}/{safe_key}", default)

    def plugin_set_setting(self, plugin_id: str, key: str, value: object) -> None:
        safe_plugin_id = self._sanitize_plugin_id(plugin_id)
        safe_key = self._sanitize_plugin_key(key)
        self._qs.setValue(f"plugins/data/{safe_plugin_id}/{safe_key}", value)

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
    def default_themes_dir(self) -> Path:
        path = self.app_data_dir / "themes"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def themes_dir(self) -> Path:
        custom = self.theme_custom_dir
        if not custom:
            return self.default_themes_dir
        try:
            path = Path(custom).expanduser()
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError:
            return self.default_themes_dir

    @property
    def default_plugins_dir(self) -> Path:
        path = self.app_data_dir / "plugins"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def plugins_dir_path(self) -> Path:
        custom = self.plugins_dir
        if not custom:
            return self.default_plugins_dir
        try:
            path = Path(custom).expanduser()
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError:
            return self.default_plugins_dir

    @staticmethod
    def _app_data_dir() -> Path:
        import os
        base = Path(os.environ.get("APPDATA", Path.home() / ".config"))
        return base / "musicorg"

    @staticmethod
    def _sanitize_plugin_id(value: str) -> str:
        cleaned = (value or "").strip().lower()
        if not cleaned:
            return "unknown-plugin"
        normalized = "".join(ch for ch in cleaned if ch.isalnum() or ch in {"-", "_"})
        return normalized or "unknown-plugin"

    @staticmethod
    def _sanitize_plugin_key(value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            return "value"
        normalized = "".join(ch for ch in cleaned if ch.isalnum() or ch in {"-", "_", "."})
        return normalized or "value"
