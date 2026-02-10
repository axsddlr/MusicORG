"""Worker for reading tags from audio files."""

from __future__ import annotations

from pathlib import Path

from musicorg.core.tagger import TagManager
from musicorg.workers.base_worker import BaseWorker


class TagReadWorker(BaseWorker):
    """Reads tags from a list of audio files in a background thread."""

    def __init__(self, paths: list[str | Path]) -> None:
        super().__init__()
        self._paths = [Path(p) for p in paths]

    def run(self) -> None:
        self.started.emit()
        try:
            tm = TagManager()
            results = []
            total = len(self._paths)
            for i, path in enumerate(self._paths):
                if self._is_cancelled:
                    self.cancelled.emit()
                    return
                try:
                    tag_data = tm.read(path)
                except Exception:
                    tag_data = None
                results.append((path, tag_data))
                self.progress.emit(i + 1, total, path.name)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))
