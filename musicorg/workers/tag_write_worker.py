"""Worker for writing tags to audio files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from musicorg.core.tagger import TagManager
from musicorg.workers.base_worker import BaseWorker

if TYPE_CHECKING:
    from musicorg.core.tagger import TagData


class TagWriteWorker(BaseWorker):
    """Writes tags to audio files in a background thread."""

    def __init__(self, items: list[tuple[str | Path, TagData]]) -> None:
        super().__init__()
        self._items = [(Path(p), td) for p, td in items]

    def run(self) -> None:
        self.started.emit()
        try:
            tm = TagManager()
            total = len(self._items)
            written = 0
            for i, (path, tag_data) in enumerate(self._items):
                if self._is_cancelled:
                    self.cancelled.emit()
                    return
                try:
                    tm.write(path, tag_data)
                    written += 1
                except Exception:
                    pass
                self.progress.emit(i + 1, total, path.name)
            self.finished.emit(written)
        except Exception as e:
            self.error.emit(str(e))
