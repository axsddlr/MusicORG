"""Walk directories and find audio files."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

AUDIO_EXTENSIONS = {".mp3", ".flac"}


@dataclass
class AudioFile:
    """Lightweight descriptor for a discovered audio file."""
    path: Path
    extension: str = field(init=False)
    size: int = field(init=False)

    def __post_init__(self) -> None:
        self.extension = self.path.suffix.lower()
        self.size = self.path.stat().st_size


class FileScanner:
    """Scans a directory tree for MP3/FLAC files."""

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
                    except OSError:
                        continue
        return results

    def scan_iter(self):
        """Yield audio files one at a time (for progress reporting)."""
        for dirpath, _dirnames, filenames in os.walk(self._root):
            for fname in sorted(filenames):
                p = Path(dirpath) / fname
                if p.suffix.lower() in AUDIO_EXTENSIONS:
                    try:
                        yield AudioFile(path=p)
                    except OSError:
                        continue
