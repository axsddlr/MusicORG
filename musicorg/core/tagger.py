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


def _coerce_artwork_bytes(value: Any) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        return data or None
    if callable(value):
        try:
            return _coerce_artwork_bytes(value())
        except Exception:
            return None
    try:
        data = bytes(value)
    except Exception:
        return None
    return data or None


def _infer_artwork_mime(artwork: Any) -> str:
    raw_mime = getattr(artwork, "mime", "") or getattr(artwork, "mime_type", "")
    if raw_mime:
        return str(raw_mime)
    fmt = str(getattr(artwork, "format", "")).strip().lower()
    if not fmt:
        return ""
    if fmt in {"jpg", "jpeg"}:
        return "image/jpeg"
    return f"image/{fmt}"


def _infer_artwork_format(mime: str) -> str | None:
    normalized = mime.strip().lower()
    if not normalized:
        return None
    if normalized in {"image/jpeg", "image/jpg"}:
        return "jpeg"
    if normalized == "image/png":
        return "png"
    if normalized == "image/webp":
        return "webp"
    if normalized == "image/bmp":
        return "bmp"
    if normalized == "image/gif":
        return "gif"
    if normalized.startswith("image/"):
        return normalized.split("/", 1)[1]
    return None


def _build_artwork(raw: bytes, mime: str) -> Any:
    fmt = _infer_artwork_format(mime)
    constructors: list[tuple[bool, Any]] = [
        (
            fmt is not None,
            lambda: music_tag.Artwork(raw=raw, fmt=fmt),
        ),
        (True, lambda: music_tag.Artwork(raw=raw)),
        (
            True,
            lambda: music_tag.Artwork(raw=raw, mime_type=mime or "image/jpeg"),
        ),
    ]
    last_error: Exception | None = None
    for enabled, constructor in constructors:
        if not enabled:
            continue
        try:
            return constructor()
        except TypeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ValueError("No supported artwork constructor available")


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
                artwork_data = _coerce_artwork_bytes(getattr(aw, "raw", None))
                if artwork_data is None:
                    artwork_data = _coerce_artwork_bytes(
                        getattr(aw, "raw_thumbnail", None)
                    )
                artwork_mime = _infer_artwork_mime(aw)
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
                    f["artwork"] = _build_artwork(
                        raw=tags.artwork_data,
                        mime=tags.artwork_mime or "image/jpeg",
                    )
                else:
                    f["artwork"] = None
            except Exception as exc:
                raise ValueError(f"Failed to embed artwork for {path}") from exc

        f.save()
