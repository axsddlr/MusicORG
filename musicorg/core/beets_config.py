"""Generate and manage beets config.yaml for the application."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from musicorg.config.settings import AppSettings


class BeetsConfigManager:
    """Generates a beets config.yaml from AppSettings and loads it."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._config_dir = settings.beets_config_dir()
        self._config_path = self._config_dir / "config.yaml"

    @property
    def config_path(self) -> Path:
        return self._config_path

    def generate(self) -> Path:
        """Write config.yaml and return its path."""
        self._config_dir.mkdir(parents=True, exist_ok=True)

        config: dict = {
            "directory": self._settings.dest_dir or "~",
            "library": self._settings.beets_db_path,
            "import": {
                "copy": True,
                "write": True,
                "log": str(self._config_dir / "import.log"),
            },
            "paths": {
                "default": self._settings.path_format,
            },
            "plugins": ["musicbrainz"],
        }

        if self._settings.discogs_token:
            config["plugins"].append("discogs")
            config["discogs"] = {
                "user_token": self._settings.discogs_token,
            }

        self._config_path.write_text(yaml.dump(config, default_flow_style=False),
                                     encoding="utf-8")
        return self._config_path

    def load(self) -> None:
        """Generate config and point beets at it."""
        config_path = self.generate()
        try:
            import beets.util.confit as confit
            beets_config = confit.Configuration("beets", read=False)
            beets_config.set_file(str(config_path))
            import beets.config
            beets.config.config = beets_config
        except Exception:
            # Beets config loading varies across versions; fall back to env var
            import os
            os.environ["BEETSDIR"] = str(self._config_dir)

        # Ensure metadata source plugins are loaded for autotag candidates.
        try:
            import beets.plugins
            from beets import metadata_plugins

            # Clear cached source discovery and load configured plugins once.
            metadata_plugins.find_metadata_source_plugins.cache_clear()
            beets.plugins.load_plugins()
            metadata_plugins.find_metadata_source_plugins.cache_clear()
        except Exception:
            pass
