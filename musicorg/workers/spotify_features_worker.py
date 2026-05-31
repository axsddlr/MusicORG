"""Worker for Spotify Audio Features fetching and tagging."""

from __future__ import annotations

from pathlib import Path

from musicorg.core.spotify_features import SpotifyFeaturesFetcher, SpotityFeaturesConfig
from musicorg.workers.base_worker import BaseWorker


class SpotifyFeaturesWorker(BaseWorker):
    """Fetches Spotify audio features and applies them to files in background."""

    def __init__(
        self,
        paths: list[str | Path],
        config: SpotityFeaturesConfig,
    ) -> None:
        super().__init__()
        self._paths = [str(p) for p in paths]
        self._config = config

    def run(self) -> None:
        self.started.emit()
        fetcher = SpotifyFeaturesFetcher(
            client_id=self._config.client_id,
            client_secret=self._config.client_secret,
        )
        total = len(self._paths)
        applied = 0
        errors: list[str] = []
        for i, path_str in enumerate(self._paths):
            if self._is_cancelled:
                self.cancelled.emit()
                return
            path = Path(path_str)
            self.progress.emit(i, total, f"Audio Features: {path.name}")
            try:
                if fetcher.apply_to_file(path, self._config):
                    applied += 1
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
        self.progress.emit(total, total, f"Applied features to {applied}/{total} files")
        self.finished.emit({"applied": applied, "total": total, "errors": errors})
