"""Read/write ID3 tags via mutagen (with beets Item as optional enhancement)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp3 import MP3


@dataclass
class TagData:
    """Clean data transfer object for audio tags."""
    title: str = ""
    artist: str = ""
    album: str = ""
    albumartist: str = ""
    track: int = 0
    disc: int = 0
    year: int = 0
    genre: str = ""
    composer: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "albumartist": self.albumartist,
            "track": self.track,
            "disc": self.disc,
            "year": self.year,
            "genre": self.genre,
            "composer": self.composer,
        }


def _first(tags: dict, key: str, default: str = "") -> str:
    """Get first value from a tag list, or default."""
    val = tags.get(key)
    if val and isinstance(val, list):
        return str(val[0])
    if val:
        return str(val)
    return default


def _first_int(tags: dict, key: str, default: int = 0) -> int:
    """Get first integer value from a tag list."""
    raw = _first(tags, key, "")
    if not raw:
        return default
    # Handle "3/12" style track numbers
    raw = raw.split("/")[0]
    try:
        return int(raw)
    except ValueError:
        return default


class TagManager:
    """Reads and writes tags for MP3 and FLAC files using mutagen."""

    def read(self, path: str | Path) -> TagData:
        """Read tags from an audio file."""
        path = Path(path)
        ext = path.suffix.lower()
        if ext == ".mp3":
            return self._read_mp3(path)
        elif ext == ".flac":
            return self._read_flac(path)
        else:
            raise ValueError(f"Unsupported format: {ext}")

    def write(self, path: str | Path, tags: TagData) -> None:
        """Write tags to an audio file."""
        path = Path(path)
        ext = path.suffix.lower()
        if ext == ".mp3":
            self._write_mp3(path, tags)
        elif ext == ".flac":
            self._write_flac(path, tags)
        else:
            raise ValueError(f"Unsupported format: {ext}")

    # -- MP3 --

    def _read_mp3(self, path: Path) -> TagData:
        try:
            audio = MP3(path, ID3=EasyID3)
        except mutagen.MutagenError:
            return TagData()
        tags = dict(audio.tags or {})
        return TagData(
            title=_first(tags, "title"),
            artist=_first(tags, "artist"),
            album=_first(tags, "album"),
            albumartist=_first(tags, "albumartist"),
            track=_first_int(tags, "tracknumber"),
            disc=_first_int(tags, "discnumber"),
            year=_first_int(tags, "date"),
            genre=_first(tags, "genre"),
            composer=_first(tags, "composer"),
        )

    def _write_mp3(self, path: Path, tags: TagData) -> None:
        try:
            audio = MP3(path, ID3=EasyID3)
        except mutagen.MutagenError:
            audio = MP3(path)
            audio.add_tags()
            audio.save()
            audio = MP3(path, ID3=EasyID3)
        audio["title"] = tags.title
        audio["artist"] = tags.artist
        audio["album"] = tags.album
        audio["albumartist"] = tags.albumartist
        audio["tracknumber"] = str(tags.track)
        audio["discnumber"] = str(tags.disc)
        audio["date"] = str(tags.year) if tags.year else ""
        audio["genre"] = tags.genre
        audio["composer"] = tags.composer
        audio.save()

    # -- FLAC --

    def _read_flac(self, path: Path) -> TagData:
        try:
            audio = FLAC(path)
        except mutagen.MutagenError:
            return TagData()
        tags = dict(audio.tags or {})
        return TagData(
            title=_first(tags, "title"),
            artist=_first(tags, "artist"),
            album=_first(tags, "album"),
            albumartist=_first(tags, "albumartist"),
            track=_first_int(tags, "tracknumber"),
            disc=_first_int(tags, "discnumber"),
            year=_first_int(tags, "date"),
            genre=_first(tags, "genre"),
            composer=_first(tags, "composer"),
        )

    def _write_flac(self, path: Path, tags: TagData) -> None:
        try:
            audio = FLAC(path)
        except mutagen.MutagenError:
            return
        audio["title"] = tags.title
        audio["artist"] = tags.artist
        audio["album"] = tags.album
        audio["albumartist"] = tags.albumartist
        audio["tracknumber"] = str(tags.track)
        audio["discnumber"] = str(tags.disc)
        audio["date"] = str(tags.year) if tags.year else ""
        audio["genre"] = tags.genre
        audio["composer"] = tags.composer
        audio.save()
