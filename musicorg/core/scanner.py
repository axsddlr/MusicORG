"""Walk directories and find audio files."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from musicorg.core.tagger import TagManager

_logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".m4a",
    ".ogg",
    ".opus",
    ".wav",
    ".aiff",
    ".wv",
    ".ape",  # Monkey's Audio
    ".tak",  # Tom's lossless Audio Kompressor
}


@dataclass
class AudioFile:
    """Lightweight descriptor for a discovered audio file."""
    path: Path
    extension: str = field(init=False)
    size: int = field(init=False)
    mtime_ns: int = field(init=False)

    def __post_init__(self) -> None:
        stat = self.path.stat()
        self.extension = self.path.suffix.lower()
        self.size = stat.st_size
        self.mtime_ns = stat.st_mtime_ns


class FileScanner:
    """Scans a directory tree for audio files."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def scan(self) -> list[AudioFile]:
        """Return all audio files under the root directory."""
        results: list[AudioFile] = []
        for dirpath, _dirnames, filenames in os.walk(self._root):
            for fname in sorted(filenames):
                p = Path(dirpath) / fname
                if p.suffix.lower() in AUDIO_EXTENSIONS:
                    try:
                        results.append(AudioFile(path=p))
                    except OSError as e:
                        _logger.debug("Skipping %s: %s", p, e)
                        continue
        return results

    def scan_iter(self) -> None:
        """Yield audio files one at a time (for progress reporting)."""
        for dirpath, _dirnames, filenames in os.walk(self._root):
            for fname in sorted(filenames):
                p = Path(dirpath) / fname
                if p.suffix.lower() in AUDIO_EXTENSIONS:
                    try:
                        yield AudioFile(path=p)
                    except OSError as e:
                        _logger.debug("Skipping %s: %s", p, e)
                        continue


class LibraryScanner:
    """Scans directories and populates a LibraryDatabase."""

    def __init__(self, root: str | Path, library_db: Any, tag_manager: TagManager | None = None) -> None:
        self._root = Path(root)
        self._library = library_db
        self._tag_manager = tag_manager or TagManager()
        self._scanned = 0
        self._updated = 0
        self._skipped = 0
        self._errors: list[str] = []

    def scan(
        self,
        progress_cb: Callable[[int, int, str], None] | None = None,
    ) -> LibraryScanResult:
        """Scan the root directory and populate the library database.

        Returns a summary of what was scanned.
        """
        self._scanned = 0
        self._updated = 0
        self._skipped = 0
        self._errors = []

        source_paths: list[Path] = []
        for dirpath, _dirnames, filenames in os.walk(self._root):
            for fname in sorted(filenames):
                p = Path(dirpath) / fname
                if p.suffix.lower() in AUDIO_EXTENSIONS:
                    source_paths.append(p)

        total = len(source_paths)
        if total == 0:
            return LibraryScanResult()

        self._library.begin_batch()
        try:
            for af_path in source_paths:
                self._scanned += 1
                if progress_cb:
                    progress_cb(self._scanned, total, af_path.name)

                try:
                    stat = af_path.stat()
                    ext = af_path.suffix.lower()
                except OSError:
                    self._skipped += 1
                    continue

                tags = self._tag_manager.read(af_path)
                self._library.upsert_track(
                    path=af_path,
                    title=tags.title,
                    artist=tags.artist,
                    album=tags.album,
                    albumartist=tags.albumartist,
                    track_number=tags.track,
                    disc_number=tags.disc,
                    year=tags.year,
                    genre=tags.genre,
                    duration=tags.duration,
                    bitrate=tags.bitrate,
                    file_size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    artwork_data=tags.artwork_data,
                    artwork_mime=tags.artwork_mime,
                )
                self._updated += 1
        finally:
            self._library.end_batch()

        old_count = self._library.total_tracks()
        self._library.remove_missing_tracks({str(p) for p in source_paths})
        removed = old_count - self._library.total_tracks()

        return LibraryScanResult(
            total=self._scanned,
            updated=self._updated,
            skipped=total - self._updated,
            removed=removed,
        )

    @property
    def errors(self) -> list[str]:
        return list(self._errors)


@dataclass
class LibraryScanResult:
    """Result summary from a LibraryScanner scan."""
    total: int = 0
    updated: int = 0
    skipped: int = 0
    removed: int = 0
