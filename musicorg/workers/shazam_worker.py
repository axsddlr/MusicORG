"""Worker for Shazam track identification."""

from __future__ import annotations

from pathlib import Path

from musicorg.core.shazam_identifier import ShazamIdentifier
from musicorg.workers.base_worker import BaseWorker


class ShazamWorker(BaseWorker):
    """Identifies tracks via Shazam audio fingerprinting in a background thread."""

    def __init__(self, paths: list[str | Path]) -> None:
        super().__init__()
        self._paths = [Path(p) for p in paths]

    def run(self) -> None:
        self.started.emit()
        identifier = ShazamIdentifier()
        total = len(self._paths)
        results: list[dict] = []
        errors: list[str] = []
        for i, path in enumerate(self._paths):
            if self._is_cancelled:
                self.cancelled.emit()
                return
            self.progress.emit(i, total, f"Shazaming: {path.name}")
            try:
                result = identifier.identify(path)
                if result:
                    results.append({
                        "path": str(path),
                        "title": result.title,
                        "artist": result.artist,
                        "album": result.album,
                        "year": result.year,
                        "genre": result.genre,
                        "isrc": result.isrc,
                        "label": result.label,
                        "cover_url": result.cover_url,
                        "match_confidence": result.match_confidence,
                    })
                else:
                    errors.append(f"No match: {path.name}")
            except Exception as exc:
                errors.append(f"Error: {path.name}: {exc}")
        self.progress.emit(total, total, "Done")
        self.finished.emit({"results": results, "errors": errors})
