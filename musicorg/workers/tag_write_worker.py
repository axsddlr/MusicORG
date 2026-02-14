"""Worker for writing tags to audio files."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from musicorg.core.tag_cache import TagCache
from musicorg.core.tagger import TagData, TagManager
from musicorg.workers.base_worker import BaseWorker


TagWriteInput = tuple[str | Path, TagData]
TagWriteFailure = tuple[Path, str]


class TagWriteSummary(TypedDict):
    written: int
    failed: list[TagWriteFailure]
    total: int


class TagWriteWorker(BaseWorker):
    """Writes tags to audio files in a background thread."""

    def __init__(
        self,
        items: list[TagWriteInput],
        *,
        cache_db_path: str = "",
    ) -> None:
        super().__init__()
        self._items = [(Path(p), td) for p, td in items]
        self._cache_db_path = cache_db_path

    def run(self) -> None:
        self.started.emit()
        try:
            tag_writer = TagManager()
            total_items = len(self._items)
            written_count = 0
            written_paths: list[Path] = []
            failed_writes: list[TagWriteFailure] = []
            for index, (path, tag_data) in enumerate(self._items):
                if self._is_cancelled:
                    self.cancelled.emit()
                    return
                try:
                    tag_writer.write(path, tag_data)
                    written_count += 1
                    written_paths.append(path)
                except Exception as exc:
                    failed_writes.append((path, str(exc) or exc.__class__.__name__))
                self.progress.emit(index + 1, total_items, path.name)

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
            self.finished.emit(
                self._build_summary(
                    written=written_count,
                    failed=failed_writes,
                    total=total_items,
                )
            )
        except Exception as exc:
            self.error.emit(str(exc))

    @staticmethod
    def _build_summary(
        *,
        written: int,
        failed: list[TagWriteFailure],
        total: int,
    ) -> TagWriteSummary:
        return {"written": written, "failed": failed, "total": total}
