"""Background workers for duplicate file detection and deletion."""

from __future__ import annotations

import logging
from pathlib import Path

_logger = logging.getLogger(__name__)

from musicorg.core.duplicate_finder import DuplicateGroup, find_duplicates
from musicorg.core.scanner import FileScanner
from musicorg.core.tag_cache import TagCache
from musicorg.core.tagger import TagData, TagManager
from musicorg.core.track_identity_index import TrackIdentityIndex
from musicorg.workers.base_worker import BaseWorker


class DuplicateScanWorker(BaseWorker):
    """Scans a directory for duplicate audio files based on tag metadata."""

    def __init__(
        self,
        root_dir: str,
        match_artist: bool = False,
        match_mode: str = "aggressive",
        identity_db_path: str = "",
        cache_db_path: str = "",
    ) -> None:
        super().__init__()
        self._root_dir = root_dir
        self._match_artist = match_artist
        self._match_mode = (match_mode or "aggressive").strip().lower()
        self._identity_db_path = identity_db_path
        self._cache_db_path = cache_db_path

    def run(self) -> None:
        self.started.emit()
        cache: TagCache | None = None
        identity_index: TrackIdentityIndex | None = None
        try:
            # Phase 1: Discover files
            self.progress.emit(0, 0, "Scanning for audio files...")
            scanner = FileScanner(self._root_dir)
            audio_files = []
            for af in scanner.scan_iter():
                if self._is_cancelled:
                    self.cancelled.emit()
                    return
                audio_files.append(af)

            if not audio_files:
                self.finished.emit([])
                return

            total = len(audio_files)

            # Open cache if available
            if self._cache_db_path:
                try:
                    cache = TagCache(self._cache_db_path)
                    cache.open()
                except Exception as e:
                    _logger.warning("Failed to open tag cache %s: %s — cache disabled", self._cache_db_path, e)
                    cache = None

            if self._identity_db_path:
                try:
                    identity_index = TrackIdentityIndex(self._identity_db_path)
                    identity_index.open()
                except Exception as e:
                    _logger.warning("Failed to open identity index %s: %s — UID matching disabled", self._identity_db_path, e)
                    identity_index = None

            # Phase 2: Read tags
            tm = TagManager()
            file_tags: list[tuple[Path, TagData, int]] = []
            track_uids: dict[Path, str] = {}
            cache_entries: list[tuple[Path, int, int, TagData]] = []

            for i, af in enumerate(audio_files):
                if self._is_cancelled:
                    self.cancelled.emit()
                    return

                self.progress.emit(i + 1, total, f"Reading tags: {af.path.name}")

                tag_data: TagData | None = None
                if cache:
                    try:
                        tag_data = cache.get(af.path, af.mtime_ns, af.size)
                    except Exception as e:
                        _logger.debug("Cache get failed for %s: %s", af.path, e)
                        tag_data = None

                if tag_data is None:
                    try:
                        tag_data = tm.read(af.path)
                        if cache:
                            cache_entries.append((af.path, af.mtime_ns, af.size, tag_data))
                    except Exception as e:
                        _logger.debug("Failed to read tags for %s: %s — skipping", af.path, e)
                        continue

                if identity_index:
                    try:
                        record = identity_index.upsert(
                            af.path,
                            af.mtime_ns,
                            af.size,
                            tag_data,
                            use_path_hints=(self._match_mode != "strict"),
                        )
                        track_uids[af.path] = record.track_uid
                    except Exception as e:
                        _logger.debug("identity_index.upsert failed for %s: %s", af.path, e)

                file_tags.append((af.path, tag_data, af.size))

            # Flush cache
            if cache and cache_entries:
                try:
                    cache.put_many(cache_entries)
                except Exception as e:
                    _logger.warning("Failed to write to tag cache: %s", e)

            # Phase 3: Find duplicates
            self.progress.emit(total, total, "Analyzing duplicates...")
            groups = find_duplicates(
                file_tags,
                match_artist=self._match_artist,
                mode=self._match_mode,
                track_uids=track_uids,
            )
            self.finished.emit(groups)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            if identity_index:
                try:
                    identity_index.close()
                except Exception as e:
                    _logger.debug("identity_index.close failed: %s", e)
            if cache:
                try:
                    cache.close()
                except Exception as e:
                    _logger.debug("cache.close failed: %s", e)


class DuplicateDeleteWorker(BaseWorker):
    """Deletes a list of files, preferring send2trash (recycle bin)."""

    def __init__(self, paths_to_delete: list[Path]) -> None:
        super().__init__()
        self._paths = list(paths_to_delete)

    def run(self) -> None:
        self.started.emit()
        try:
            _send2trash = None
            try:
                from send2trash import send2trash as _send2trash
            except ImportError:
                _send2trash = None

            deleted = 0
            failed: list[str] = []
            total = len(self._paths)

            for i, path in enumerate(self._paths):
                if self._is_cancelled:
                    self.cancelled.emit()
                    return

                self.progress.emit(i + 1, total, f"Deleting: {path.name}")

                try:
                    if _send2trash is not None:
                        _send2trash(str(path))
                    else:
                        path.unlink()
                    deleted += 1
                except Exception as e:
                    # Fallback: try unlink if send2trash failed
                    if _send2trash is not None:
                        try:
                            path.unlink()
                            deleted += 1
                            continue
                        except Exception:
                            pass
                    failed.append(f"{path}: {e}")

            self.finished.emit({"deleted": deleted, "failed": failed})

        except Exception as e:
            self.error.emit(str(e))
