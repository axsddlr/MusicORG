"""Worker for reading tags from audio files."""

from __future__ import annotations

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import os
from pathlib import Path
import threading
from typing import TypedDict

from PySide6.QtCore import Signal

from musicorg.core.tag_cache import TagCache
from musicorg.core.tagger import TagData, TagManager
from musicorg.workers.base_worker import BaseWorker


TagBatchEntry = tuple[Path, TagData | None]
TagReadFailure = tuple[Path, str]
CacheWriteEntry = tuple[Path, int, int, TagData]


class TagReadFinishedPayload(TypedDict):
    results: list[TagBatchEntry]
    failures: list[TagReadFailure]
    cache_hits: int
    cache_misses: int


@dataclass(slots=True)
class TagReadOutcome:
    index: int
    path: Path
    tags: TagData | None
    error_message: str
    file_size: int
    modified_time_ns: int
    cache_hit: bool
    cache_miss: bool


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
        shared_cache: TagCache | None = None
        executor: ThreadPoolExecutor | None = None
        try:
            total_paths = len(self._paths)
            if total_paths == 0:
                self.finished.emit(self._empty_payload())
                return

            batch_results: list[TagBatchEntry] = [(path, None) for path in self._paths]
            failures: list[TagReadFailure] = []
            pending_cache_writes: list[CacheWriteEntry] = []
            cache_hits = 0
            cache_misses = 0
            pending_batch_rows: list[TagBatchEntry] = []

            if self._cache_db_path:
                try:
                    shared_cache = TagCache(self._cache_db_path)
                    shared_cache.open()
                except Exception:
                    shared_cache = None

            max_workers = min(os.cpu_count() or 4, 8)
            executor = ThreadPoolExecutor(max_workers=max_workers)
            futures: list[Future[TagReadOutcome]] = [
                executor.submit(self._read_one, i, path)
                for i, path in enumerate(self._paths)
            ]
            completed_count = 0
            was_cancelled = False

            for future in as_completed(futures):
                if self._is_cancelled:
                    was_cancelled = True
                    for pending in futures:
                        pending.cancel()
                    break

                try:
                    outcome = future.result()
                except CancelledError:
                    continue

                batch_results[outcome.index] = (outcome.path, outcome.tags)
                if outcome.cache_hit:
                    cache_hits += 1
                if outcome.cache_miss:
                    cache_misses += 1
                if outcome.error_message:
                    failures.append((outcome.path, outcome.error_message))
                if (
                    outcome.tags is not None
                    and shared_cache is not None
                    and outcome.file_size
                    and outcome.modified_time_ns
                ):
                    pending_cache_writes.append(
                        (
                            outcome.path,
                            outcome.modified_time_ns,
                            outcome.file_size,
                            outcome.tags,
                        )
                    )

                pending_batch_rows.append((outcome.path, outcome.tags))
                completed_count += 1
                self.progress.emit(completed_count, total_paths, outcome.path.name)
                if len(pending_batch_rows) >= self._BATCH_SIZE:
                    self.batch_ready.emit(pending_batch_rows.copy())
                    pending_batch_rows.clear()

            if was_cancelled:
                self.cancelled.emit()
                return

            if pending_batch_rows:
                self.batch_ready.emit(pending_batch_rows.copy())

            if shared_cache and pending_cache_writes:
                try:
                    shared_cache.put_many(pending_cache_writes)
                except Exception:
                    pass
            self.finished.emit(
                self._build_finished_payload(
                    results=batch_results,
                    failures=failures,
                    cache_hits=cache_hits,
                    cache_misses=cache_misses,
                )
            )
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if executor:
                executor.shutdown(wait=True, cancel_futures=True)
            self._close_thread_caches()
            if shared_cache:
                try:
                    shared_cache.close()
                except Exception:
                    pass

    def _read_one(
        self,
        index: int,
        path: Path,
    ) -> TagReadOutcome:
        file_size = self._sizes[index] if index < len(self._sizes) else 0
        modified_time_ns = self._mtimes_ns[index] if index < len(self._mtimes_ns) else 0
        if not file_size or not modified_time_ns:
            try:
                stat = path.stat()
                if not file_size:
                    file_size = stat.st_size
                if not modified_time_ns:
                    modified_time_ns = stat.st_mtime_ns
            except OSError:
                pass

        tag_data: TagData | None = None
        was_cache_hit = False
        was_cache_miss = False
        thread_cache = self._thread_cache()
        if thread_cache and file_size and modified_time_ns:
            try:
                tag_data = thread_cache.get(path, modified_time_ns, file_size)
            except Exception:
                tag_data = None

        if tag_data is not None:
            was_cache_hit = True
            return TagReadOutcome(
                index=index,
                path=path,
                tags=tag_data,
                error_message="",
                file_size=file_size,
                modified_time_ns=modified_time_ns,
                cache_hit=was_cache_hit,
                cache_miss=was_cache_miss,
            )

        was_cache_miss = True
        try:
            tag_data = self._thread_tagger().read(path)
            return TagReadOutcome(
                index=index,
                path=path,
                tags=tag_data,
                error_message="",
                file_size=file_size,
                modified_time_ns=modified_time_ns,
                cache_hit=was_cache_hit,
                cache_miss=was_cache_miss,
            )
        except Exception as exc:
            return TagReadOutcome(
                index=index,
                path=path,
                tags=None,
                error_message=str(exc) or exc.__class__.__name__,
                file_size=file_size,
                modified_time_ns=modified_time_ns,
                cache_hit=was_cache_hit,
                cache_miss=was_cache_miss,
            )

    def _thread_tagger(self) -> TagManager:
        tag_reader = getattr(self._thread_local, "tagger", None)
        if tag_reader is None:
            tag_reader = TagManager()
            self._thread_local.tagger = tag_reader
        return tag_reader

    def _thread_cache(self) -> TagCache | None:
        has_initialized_cache = getattr(self._thread_local, "cache_initialized", False)
        if has_initialized_cache:
            return getattr(self._thread_local, "cache", None)

        thread_cache: TagCache | None = None
        if self._cache_db_path:
            try:
                thread_cache = TagCache(self._cache_db_path)
                thread_cache.open()
            except Exception:
                thread_cache = None

        self._thread_local.cache = thread_cache
        self._thread_local.cache_initialized = True
        if thread_cache is not None:
            with self._thread_caches_lock:
                self._thread_caches.append(thread_cache)
        return thread_cache

    def _close_thread_caches(self) -> None:
        with self._thread_caches_lock:
            thread_caches = list(self._thread_caches)
            self._thread_caches.clear()
        for thread_cache in thread_caches:
            try:
                thread_cache.close()
            except Exception:
                pass

    @staticmethod
    def _empty_payload() -> TagReadFinishedPayload:
        return {
            "results": [],
            "failures": [],
            "cache_hits": 0,
            "cache_misses": 0,
        }

    @staticmethod
    def _build_finished_payload(
        *,
        results: list[TagBatchEntry],
        failures: list[TagReadFailure],
        cache_hits: int,
        cache_misses: int,
    ) -> TagReadFinishedPayload:
        return {
            "results": results,
            "failures": failures,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
        }
