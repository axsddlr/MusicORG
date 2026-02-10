"""Application settings via QSettings."""

from __future__ import annotations

from pathlib import Path

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

    # -- beets db --

    @property
    def beets_db_path(self) -> str:
        default = str(self._app_data_dir() / "beets" / "library.db")
        return self._qs.value("beets/db_path", default, type=str)

    @beets_db_path.setter
    def beets_db_path(self, value: str) -> None:
        self._qs.setValue("beets/db_path", value)

    # -- window geometry --

    @property
    def window_geometry(self) -> bytes | None:
        return self._qs.value("ui/window_geometry")

    @window_geometry.setter
    def window_geometry(self, value: bytes) -> None:
        self._qs.setValue("ui/window_geometry", value)

    # -- helpers --

    @staticmethod
    def _app_data_dir() -> Path:
        import os
        base = Path(os.environ.get("APPDATA", Path.home() / ".config"))
        return base / "musicorg"

    def beets_config_dir(self) -> Path:
        return self._app_data_dir() / "beets"
