"""Worker for writing tags to audio files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from musicorg.core.tag_cache import TagCache
from musicorg.core.tagger import TagManager
from musicorg.workers.base_worker import BaseWorker

if TYPE_CHECKING:
    from musicorg.core.tagger import TagData


class TagWriteWorker(BaseWorker):
    """Writes tags to audio files in a background thread."""

    def __init__(
        self,
        items: list[tuple[str | Path, TagData]],
        *,
        cache_db_path: str = "",
    ) -> None:
        super().__init__()
        self._items = [(Path(p), td) for p, td in items]
        self._cache_db_path = cache_db_path

    def run(self) -> None:
        self.started.emit()
        try:
            tm = TagManager()
            total = len(self._items)
            written = 0
            written_paths: list[Path] = []
            failed: list[tuple[Path, str]] = []
            for i, (path, tag_data) in enumerate(self._items):
                if self._is_cancelled:
                    self.cancelled.emit()
                    return
                try:
                    tm.write(path, tag_data)
                    written += 1
                    written_paths.append(path)
                except Exception as e:
                    failed.append((path, str(e) or e.__class__.__name__))
                self.progress.emit(i + 1, total, path.name)

            if self._cache_db_path and written_paths:
                cache: TagCache | None = None
                try:
                    cache = TagCache(self._cache_db_path)
                    cache.open()
                    cache.invalidate_many(written_paths)
                except Exception:
                    pass
                finally:
                    if cache:
                        try:
                            cache.close()
                        except Exception:
                            pass
            self.finished.emit({"written": written, "failed": failed, "total": total})
        except Exception as e:
            self.error.emit(str(e))
