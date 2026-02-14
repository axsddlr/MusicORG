"""Worker for reading tags from audio files."""

from __future__ import annotations

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import threading
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal

from musicorg.core.tag_cache import TagCache
from musicorg.core.tagger import TagManager
from musicorg.workers.base_worker import BaseWorker

if TYPE_CHECKING:
    from musicorg.core.tagger import TagData


class TagReadWorker(BaseWorker):
    """Reads tags from a list of audio files in a background thread."""

    batch_ready = Signal(list)
    _BATCH_SIZE = 50

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
        self._thread_local = threading.local()
        self._thread_caches: list[TagCache] = []
        self._thread_caches_lock = threading.Lock()

    def run(self) -> None:
        self.started.emit()
        cache: TagCache | None = None
        executor: ThreadPoolExecutor | None = None
        try:
            total = len(self._paths)
            if total == 0:
                self.finished.emit(
                    {
                        "results": [],
                        "failures": [],
                        "cache_hits": 0,
                        "cache_misses": 0,
                    }
                )
                return

            results: list[tuple[Path, TagData | None]] = [
                (path, None) for path in self._paths
            ]
            failures: list[tuple[Path, str]] = []
            cache_entries: list[tuple[Path, int, int, TagData]] = []
            cache_hits = 0
            cache_misses = 0
            pending_batch: list[tuple[Path, TagData | None]] = []

            if self._cache_db_path:
                try:
                    cache = TagCache(self._cache_db_path)
                    cache.open()
                except Exception:
                    cache = None

            max_workers = min(os.cpu_count() or 4, 8)
            executor = ThreadPoolExecutor(max_workers=max_workers)
            futures: list[Future[tuple[int, Path, TagData | None, str, int, int, bool, bool]]] = [
                executor.submit(self._read_one, i, path)
                for i, path in enumerate(self._paths)
            ]
            completed = 0
            cancelled = False

            for future in as_completed(futures):
                if self._is_cancelled:
                    cancelled = True
                    for pending in futures:
                        pending.cancel()
                    break

                try:
                    (
                        index,
                        path,
                        tag_data,
                        error,
                        size,
                        mtime_ns,
                        was_cache_hit,
                        was_cache_miss,
                    ) = future.result()
                except CancelledError:
                    continue

                results[index] = (path, tag_data)
                if was_cache_hit:
                    cache_hits += 1
                if was_cache_miss:
                    cache_misses += 1
                if error:
                    failures.append((path, error))
                if tag_data is not None and cache and size and mtime_ns:
                    cache_entries.append((path, mtime_ns, size, tag_data))

                pending_batch.append((path, tag_data))
                completed += 1
                self.progress.emit(completed, total, path.name)
                if len(pending_batch) >= self._BATCH_SIZE:
                    self.batch_ready.emit(pending_batch.copy())
                    pending_batch.clear()

            if cancelled:
                self.cancelled.emit()
                return

            if pending_batch:
                self.batch_ready.emit(pending_batch.copy())

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
            if executor:
                executor.shutdown(wait=True, cancel_futures=True)
            self._close_thread_caches()
            if cache:
                try:
                    cache.close()
                except Exception:
                    pass

    def _read_one(
        self,
        index: int,
        path: Path,
    ) -> tuple[int, Path, TagData | None, str, int, int, bool, bool]:
        size = self._sizes[index] if index < len(self._sizes) else 0
        mtime_ns = self._mtimes_ns[index] if index < len(self._mtimes_ns) else 0
        if not size or not mtime_ns:
            try:
                stat = path.stat()
                if not size:
                    size = stat.st_size
                if not mtime_ns:
                    mtime_ns = stat.st_mtime_ns
            except OSError:
                pass

        tag_data: TagData | None = None
        cache_hit = False
        cache_miss = False
        cache = self._thread_cache()
        if cache and size and mtime_ns:
            try:
                tag_data = cache.get(path, mtime_ns, size)
            except Exception:
                tag_data = None

        if tag_data is not None:
            cache_hit = True
            return (index, path, tag_data, "", size, mtime_ns, cache_hit, cache_miss)

        cache_miss = True
        try:
            tag_data = self._thread_tagger().read(path)
            return (index, path, tag_data, "", size, mtime_ns, cache_hit, cache_miss)
        except Exception as exc:
            return (
                index,
                path,
                None,
                str(exc) or exc.__class__.__name__,
                size,
                mtime_ns,
                cache_hit,
                cache_miss,
            )

    def _thread_tagger(self) -> TagManager:
        tagger = getattr(self._thread_local, "tagger", None)
        if tagger is None:
            tagger = TagManager()
            self._thread_local.tagger = tagger
        return tagger

    def _thread_cache(self) -> TagCache | None:
        initialized = getattr(self._thread_local, "cache_initialized", False)
        if initialized:
            return getattr(self._thread_local, "cache", None)

        cache: TagCache | None = None
        if self._cache_db_path:
            try:
                cache = TagCache(self._cache_db_path)
                cache.open()
            except Exception:
                cache = None

        self._thread_local.cache = cache
        self._thread_local.cache_initialized = True
        if cache is not None:
            with self._thread_caches_lock:
                self._thread_caches.append(cache)
        return cache

    def _close_thread_caches(self) -> None:
        with self._thread_caches_lock:
            caches = list(self._thread_caches)
            self._thread_caches.clear()
        for cache in caches:
            try:
                cache.close()
            except Exception:
                pass
