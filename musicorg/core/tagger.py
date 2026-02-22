"""Read/write audio tags via music-tag."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import music_tag


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
    comment: str = ""
    lyrics: str = ""
    duration: float = 0.0
    bitrate: int = 0
    artwork_data: bytes | None = None
    artwork_mime: str = ""

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
            "comment": self.comment,
            "lyrics": self.lyrics,
            "duration": self.duration,
            "bitrate": self.bitrate,
            "artwork_data": self.artwork_data,
            "artwork_mime": self.artwork_mime,
        }


def _str(f: Any, key: str) -> str:
    try:
        val = f[key].first
        return str(val) if val is not None else ""
    except Exception:
        return ""


def _int(f: Any, key: str) -> int:
    try:
        val = f[key].first
        if val is None:
            return 0
        return int(val)
    except Exception:
        return 0


def _float(f: Any, key: str) -> float:
    try:
        val = f[key].first
        if val is None:
            return 0.0
        return float(val)
    except Exception:
        return 0.0


class TagManager:
    """Reads and writes tags for audio files using music-tag."""

    def read(self, path: str | Path) -> TagData:
        """Read tags from an audio file."""
        try:
            f = music_tag.load_file(str(path))
        except Exception:
            return TagData()

        artwork_data: bytes | None = None
        artwork_mime = ""
        try:
            aw = f["artwork"].first
            if aw is not None:
                artwork_data = bytes(aw.raw_thumbnail)
                artwork_mime = str(aw.mime_type or "")
        except Exception:
            pass

        return TagData(
            title=_str(f, "tracktitle"),
            artist=_str(f, "artist"),
            album=_str(f, "album"),
            albumartist=_str(f, "albumartist"),
            track=_int(f, "tracknumber"),
            disc=_int(f, "discnumber"),
            year=_int(f, "year"),
            genre=_str(f, "genre"),
            composer=_str(f, "composer"),
            comment=_str(f, "comment"),
            lyrics=_str(f, "lyrics"),
            duration=_float(f, "#length"),
            bitrate=_int(f, "#bitrate"),
            artwork_data=artwork_data,
            artwork_mime=artwork_mime,
        )

    def write(self, path: str | Path, tags: TagData) -> None:
        """Write tags to an audio file."""
        try:
            f = music_tag.load_file(str(path))
        except Exception as exc:
            raise ValueError(f"Cannot open file for writing: {path}") from exc

        f["tracktitle"] = tags.title
        f["artist"] = tags.artist
        f["album"] = tags.album
        f["albumartist"] = tags.albumartist
        f["tracknumber"] = tags.track
        f["discnumber"] = tags.disc
        f["year"] = tags.year
        f["genre"] = tags.genre
        f["composer"] = tags.composer
        f["comment"] = tags.comment
        f["lyrics"] = tags.lyrics

        if tags.artwork_data is not None:
            try:
                if tags.artwork_data:
                    f["artwork"] = music_tag.Artwork(
                        raw=tags.artwork_data,
                        mime_type=tags.artwork_mime or "image/jpeg",
                    )
                else:
                    f["artwork"] = None
            except Exception:
                pass

        f.save()
