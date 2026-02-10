"""Thin wrapper around beets.library.Library."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from musicorg.config.settings import AppSettings


class LibraryManager:
    """Manages a beets Library instance."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._lib = None

    @property
    def lib(self):
        """Lazy-initialize and return the beets Library."""
        if self._lib is None:
            self._lib = self._open()
        return self._lib

    def _open(self):
        db_path = self._settings.beets_db_path
        dest_dir = self._settings.dest_dir or str(Path.home() / "Music")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            from beets.library import Library
            return Library(db_path, dest_dir)
        except Exception:
            return None

    def close(self) -> None:
        if self._lib is not None:
            try:
                self._lib.close()
            except Exception:
                pass
            self._lib = None
