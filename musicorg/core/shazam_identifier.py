"""Identify tracks without metadata via Shazam audio fingerprinting."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ShazamResult:
    """Result from Shazam track identification."""

    title: str = ""
    artist: str = ""
    album: str = ""
    year: int = 0
    genre: str = ""
    isrc: str = ""
    label: str = ""
    cover_url: str = ""
    match_confidence: float = 0.0
    raw: dict = field(default_factory=dict)


class ShazamIdentifier:
    """Identify audio tracks via Shazam's audio fingerprinting API."""

    def identify(self, path: str | Path) -> ShazamResult | None:
        path = Path(path)
        if not path.exists():
            return None
        try:
            return asyncio.run(self._identify_async(path))
        except Exception:
            return None

    @staticmethod
    async def _identify_async(path: Path) -> ShazamResult | None:
        from shazamio import Shazam

        shazam = Shazam()
        try:
            result = await shazam.recognize(str(path))
        except Exception:
            return None

        track = result.get("track", {})
        if not track:
            return None

        title = str(track.get("title", "") or "")
        subtitle = str(track.get("subtitle", "") or "")
        artist = subtitle if subtitle else ""
        sections = track.get("sections", [])
        metadata_list: list[dict] = []
        for section in sections:
            if isinstance(section, dict) and section.get("type") == "SONG":
                metadata_list = section.get("metadata", []) or []
                break

        album = ""
        year = 0
        genre = ""
        isrc = ""
        label = ""
        cover_url = ""

        for meta in metadata_list:
            if not isinstance(meta, dict):
                continue
            meta_text = str(meta.get("text", "") or "")
            meta_title = str(meta.get("title", "") or "")
            if meta_title == "Album":
                album = meta_text
            elif meta_title == "Released":
                try:
                    year = int(meta_text[:4])
                except (ValueError, IndexError):
                    pass
            elif meta_title == "Genre":
                genre = meta_text
            elif meta_title == "ISRC":
                isrc = meta_text
            elif meta_title == "Label":
                label = meta_text

        images = track.get("images", {})
        if isinstance(images, dict):
            cover_url = str(
                images.get("coverarthq") or images.get("coverart") or ""
            )

        match_confidence = 1.0
        if title and artist:
            match_confidence = 0.85
        elif title:
            match_confidence = 0.5

        return ShazamResult(
            title=title,
            artist=artist,
            album=album,
            year=year,
            genre=genre,
            isrc=isrc,
            label=label,
            cover_url=cover_url,
            match_confidence=match_confidence,
            raw=result,
        )
