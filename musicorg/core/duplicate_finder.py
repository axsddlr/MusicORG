"""Find duplicate audio files by tag metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from musicorg.core.tagger import TagData

FORMAT_PRIORITY: dict[str, int] = {
    ".flac": 2,
    ".mp3": 1,
}


def normalize_title(title: str) -> str:
    """Lowercase, strip, and collapse whitespace."""
    return re.sub(r"\s+", " ", title.strip().lower())


@dataclass
class DuplicateFile:
    """One file within a duplicate group."""

    path: Path
    tags: TagData
    extension: str
    size: int
    keep: bool = False


@dataclass
class DuplicateGroup:
    """A set of files sharing the same normalized title (and optionally artist)."""

    normalized_key: str
    files: list[DuplicateFile] = field(default_factory=list)

    @property
    def kept_file(self) -> DuplicateFile | None:
        for f in self.files:
            if f.keep:
                return f
        return None

    @property
    def deletable_files(self) -> list[DuplicateFile]:
        return [f for f in self.files if not f.keep]


def find_duplicates(
    file_tags: list[tuple[Path, TagData, int]],
    *,
    match_artist: bool = False,
) -> list[DuplicateGroup]:
    """Find duplicate audio files by tag title.

    Args:
        file_tags: List of (path, TagData, file_size) tuples.
        match_artist: If True, group by (title + artist) instead of title alone.

    Returns:
        List of DuplicateGroup, each containing 2+ files with the same key.
    """
    groups: dict[str, list[DuplicateFile]] = {}

    for path, tags, size in file_tags:
        title = normalize_title(tags.title)
        if not title:
            continue

        if match_artist:
            artist = normalize_title(tags.artist)
            key = f"{title} || {artist}"
        else:
            key = title

        ext = path.suffix.lower()
        df = DuplicateFile(path=path, tags=tags, extension=ext, size=size)
        groups.setdefault(key, []).append(df)

    # Filter to groups with 2+ files
    result: list[DuplicateGroup] = []
    for key, files in groups.items():
        if len(files) < 2:
            continue

        # Sort: highest format priority first, then largest size first
        files.sort(
            key=lambda f: (FORMAT_PRIORITY.get(f.extension, 0), f.size),
            reverse=True,
        )

        # First file is kept, rest are marked for deletion
        files[0].keep = True
        for f in files[1:]:
            f.keep = False

        result.append(DuplicateGroup(normalized_key=key, files=files))

    # Sort groups by key for stable output
    result.sort(key=lambda g: g.normalized_key)
    return result
