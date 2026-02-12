"""Worker for reading tags from audio files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from musicorg.core.tag_cache import TagCache
from musicorg.core.tagger import TagManager
from musicorg.workers.base_worker import BaseWorker

if TYPE_CHECKING:
    from musicorg.core.tagger import TagData


class TagReadWorker(BaseWorker):
    """Reads tags from a list of audio files in a background thread."""

    def __init__(
        self,
        paths: list[str | Path],
        *,
        sizes: list[int] | None = None,
        mtimes_ns: list[int] | None = None,
        cache_db_path: str = "",
    ) -> None:
        super().__init__()
        self._paths = [Path(p) for p in paths]
        self._sizes = list(sizes or [])
        self._mtimes_ns = list(mtimes_ns or [])
        self._cache_db_path = cache_db_path

    def run(self) -> None:
        self.started.emit()
        cache: TagCache | None = None
        try:
            tm = TagManager()
            results = []
            failures: list[tuple[Path, str]] = []
            cache_entries: list[tuple[Path, int, int, TagData]] = []
            cache_hits = 0
            cache_misses = 0
            if self._cache_db_path:
                try:
                    cache = TagCache(self._cache_db_path)
                    cache.open()
                except Exception:
                    cache = None
            total = len(self._paths)
            for i, path in enumerate(self._paths):
                if self._is_cancelled:
                    self.cancelled.emit()
                    return

                size = self._sizes[i] if i < len(self._sizes) else 0
                mtime_ns = self._mtimes_ns[i] if i < len(self._mtimes_ns) else 0
                if not size or not mtime_ns:
                    try:
                        stat = path.stat()
                        if not size:
                            size = stat.st_size
                        if not mtime_ns:
                            mtime_ns = stat.st_mtime_ns
                    except OSError:
                        pass

                tag_data = None
                if cache and size and mtime_ns:
                    try:
                        tag_data = cache.get(path, mtime_ns, size)
                    except Exception:
                        tag_data = None

                if tag_data is not None:
                    cache_hits += 1
                else:
                    cache_misses += 1
                    try:
                        tag_data = tm.read(path)
                        if cache and size and mtime_ns:
                            cache_entries.append((path, mtime_ns, size, tag_data))
                    except Exception as e:
                        failures.append((path, str(e) or e.__class__.__name__))

                results.append((path, tag_data))
                self.progress.emit(i + 1, total, path.name)
            if cache and cache_entries:
                try:
                    cache.put_many(cache_entries)
                except Exception:
                    pass
            self.finished.emit(
                {
                    "results": results,
                    "failures": failures,
                    "cache_hits": cache_hits,
                    "cache_misses": cache_misses,
                }
            )
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if cache:
                try:
                    cache.close()
                except Exception:
                    pass
