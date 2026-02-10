"""MusicBrainz/Discogs lookup via beets autotag API."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any
from urllib.request import Request, urlopen


_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


@dataclass
class MatchCandidate:
    """A single match candidate from MusicBrainz or Discogs."""
    source: str = ""          # "MusicBrainz" or "Discogs"
    artist: str = ""
    album: str = ""
    year: int = 0
    distance: float = 1.0     # 0.0 = perfect, 1.0 = worst
    tracks: list[dict[str, Any]] = field(default_factory=list)
    raw_match: Any = None      # Original beets match object for apply

    @property
    def match_percent(self) -> float:
        return round((1.0 - self.distance) * 100, 1)


class AutoTagger:
    """Wraps beets autotag API for album and item matching."""

    def search_album(self, paths: list[str | Path],
                     artist_hint: str = "",
                     album_hint: str = "") -> list[MatchCandidate]:
        """Search MusicBrainz/Discogs for album matches.

        Args:
            paths: List of audio file paths (one album's worth).
            artist_hint: Optional artist name to narrow search.
            album_hint: Optional album name to narrow search.

        Returns:
            List of MatchCandidate sorted by distance (best first).
        """
        if not paths:
            return []
        try:
            return self._search_album_beets(paths, artist_hint, album_hint)
        except Exception as exc:
            raise RuntimeError(f"Album search failed: {exc}") from exc

    def search_item(self, path: str | Path,
                    artist_hint: str = "",
                    title_hint: str = "") -> list[MatchCandidate]:
        """Search for single-track matches."""
        if not Path(path).exists():
            return []
        try:
            return self._search_item_beets(path, artist_hint, title_hint)
        except Exception as exc:
            raise RuntimeError(f"Single-item search failed: {exc}") from exc

    def apply_match(self, paths: list[str | Path],
                    match: MatchCandidate) -> bool:
        """Apply a match's metadata to the files."""
        try:
            return self._apply_match_beets(paths, match)
        except Exception as exc:
            raise RuntimeError(f"Apply match failed: {exc}") from exc

    # -- beets implementation --

    def _search_album_beets(self, paths, artist_hint, album_hint):
        from beets import autotag
        from beets.library import Item

        if not paths:
            return []

        items = []
        for p in paths:
            item = Item.from_path(str(p))
            item.read()
            items.append(item)

        artist = artist_hint or items[0].albumartist or items[0].artist or ""
        album = album_hint or items[0].album or ""

        result = autotag.tag_album(items, artist, album)
        candidates = self._extract_candidates(result)

        results: list[MatchCandidate] = []
        for c in candidates:
            dist = getattr(c, 'distance', None)
            distance = float(dist) if dist is not None else 1.0
            info = getattr(c, 'info', c)
            tracks_data = []
            track_list = getattr(info, 'tracks', [])
            for t in track_list:
                tracks_data.append({
                    "track": getattr(t, 'index', 0),
                    "title": getattr(t, 'title', ''),
                    "artist": getattr(t, 'artist', ''),
                    "length": getattr(t, 'length', 0),
                })

            source = "MusicBrainz"
            data_source = getattr(info, 'data_source', '')
            if 'discogs' in str(data_source).lower():
                source = "Discogs"

            results.append(MatchCandidate(
                source=source,
                artist=getattr(info, 'artist', ''),
                album=getattr(info, 'album', ''),
                year=getattr(info, 'year', 0) or 0,
                distance=distance,
                tracks=tracks_data,
                raw_match=c,
            ))

        results.sort(key=lambda m: m.distance)
        return results

    def _search_item_beets(self, path, artist_hint, title_hint):
        from beets import autotag
        from beets.library import Item

        item = Item.from_path(str(path))
        item.read()

        artist = artist_hint or item.artist or ""
        title = title_hint or item.title or ""

        result = autotag.tag_item(item, artist, title)
        candidates = self._extract_candidates(result)

        results: list[MatchCandidate] = []
        for c in candidates:
            dist = getattr(c, 'distance', None)
            distance = float(dist) if dist is not None else 1.0
            info = getattr(c, 'info', c)

            source = "MusicBrainz"
            data_source = getattr(info, 'data_source', '')
            if 'discogs' in str(data_source).lower():
                source = "Discogs"

            results.append(MatchCandidate(
                source=source,
                artist=getattr(info, 'artist', ''),
                album=getattr(info, 'album', ''),
                year=getattr(info, 'year', 0) or 0,
                distance=distance,
                raw_match=c,
            ))

        results.sort(key=lambda m: m.distance)
        return results

    def _apply_match_beets(self, paths, match: MatchCandidate) -> bool:
        from beets import autotag
        from beets.library import Item

        raw = match.raw_match
        if raw is None:
            return False

        items = []
        for p in paths:
            item = Item.from_path(str(p))
            item.read()
            items.append(item)

        info = getattr(raw, 'info', raw)
        artwork = self._download_artwork(info)
        artwork_data = artwork[0] if artwork else None
        artwork_mime = artwork[1] if artwork else ""

        # Apply metadata from the match to the items
        try:
            # AlbumMatch path
            item_info_pairs = getattr(raw, 'item_info_pairs', None)
            mapping = getattr(raw, 'mapping', None)
            if item_info_pairs:
                autotag.apply_metadata(info, list(item_info_pairs))
            elif mapping:
                autotag.apply_metadata(info, list(mapping.items()))
            else:
                # TrackMatch (or fallback): apply same track info to each item.
                for item in items:
                    autotag.apply_item_metadata(item, info)
        except Exception:
            # Fallback: manually apply key fields
            for item in items:
                item.albumartist = info.artist if hasattr(info, 'artist') else ''
                item.album = info.album if hasattr(info, 'album') else ''
                item.year = info.year if hasattr(info, 'year') else 0

        # Write tags to files
        from musicorg.core.tagger import TagManager, TagData
        tm = TagManager()
        for item in items:
            td = TagData(
                title=getattr(item, 'title', '') or '',
                artist=getattr(item, 'artist', '') or '',
                album=getattr(item, 'album', '') or '',
                albumartist=getattr(item, 'albumartist', '') or '',
                track=getattr(item, 'track', 0) or 0,
                disc=getattr(item, 'disc', 0) or 0,
                year=getattr(item, 'year', 0) or 0,
                genre=getattr(item, 'genre', '') or '',
                composer=getattr(item, 'composer', '') or '',
                artwork_data=artwork_data,
                artwork_mime=artwork_mime,
            )
            tm.write(item.path if isinstance(item.path, (str, Path)) else item.path.decode(), td)

        return True

    @staticmethod
    def _extract_candidates(result: Any) -> list[Any]:
        """Normalize beets tag_* return values across versions."""
        if result is None:
            return []

        # beets Proposal (modern API)
        candidates = getattr(result, "candidates", None)
        if candidates is not None:
            return list(candidates)

        # Legacy tuple formats:
        # - (artist, album, candidates, recommendation)
        # - (artist, album, proposal)
        if isinstance(result, tuple):
            if len(result) >= 3:
                third = result[2]
                third_candidates = getattr(third, "candidates", None)
                if third_candidates is not None:
                    return list(third_candidates)
                if len(result) >= 4:
                    return list(result[2] or [])
            return []

        # Direct iterable candidate stream
        if hasattr(result, "__iter__") and not isinstance(result, (str, bytes, dict)):
            return list(result)

        # Single candidate object
        return [result]

    @classmethod
    def _candidate_artwork_urls(cls, info: Any) -> list[str]:
        urls: list[str] = []

        cover_art_url = str(getattr(info, "cover_art_url", "") or "").strip()
        if cover_art_url:
            urls.append(cover_art_url)

        data_source = str(getattr(info, "data_source", "") or "").lower()
        if "musicbrainz" in data_source:
            data_url = str(getattr(info, "data_url", "") or "")
            album_id = str(getattr(info, "album_id", "") or "")
            releasegroup_id = str(getattr(info, "releasegroup_id", "") or "")

            release_id = cls._extract_mb_entity_id(data_url, "release")
            if not release_id and cls._is_uuid(album_id):
                release_id = album_id

            rg_id = cls._extract_mb_entity_id(data_url, "release-group")
            if not rg_id and cls._is_uuid(releasegroup_id):
                rg_id = releasegroup_id

            if release_id:
                urls.extend([
                    f"https://coverartarchive.org/release/{release_id}/front-500",
                    f"https://coverartarchive.org/release/{release_id}/front",
                ])
            if rg_id:
                urls.extend([
                    f"https://coverartarchive.org/release-group/{rg_id}/front-500",
                    f"https://coverartarchive.org/release-group/{rg_id}/front",
                ])

        # Preserve order while de-duplicating.
        deduped: list[str] = []
        seen: set[str] = set()
        for url in urls:
            if url and url not in seen:
                seen.add(url)
                deduped.append(url)
        return deduped

    @classmethod
    def _download_artwork(cls, info: Any) -> tuple[bytes, str] | None:
        for url in cls._candidate_artwork_urls(info):
            try:
                req = Request(url, headers={"User-Agent": "MusicOrg/0.1"})
                with urlopen(req, timeout=12) as resp:
                    data = resp.read()
                    if not data:
                        continue
                    mime = cls._normalize_content_type(resp.headers.get("Content-Type", ""))
                    if not mime:
                        mime = cls._guess_image_mime(data)
                    if not mime:
                        mime = "image/jpeg"
                    return data, mime
            except Exception:
                continue
        return None

    @staticmethod
    def _normalize_content_type(content_type: str) -> str:
        if not content_type:
            return ""
        mime = content_type.split(";", 1)[0].strip().lower()
        return mime if mime.startswith("image/") else ""

    @staticmethod
    def _guess_image_mime(data: bytes) -> str:
        if data.startswith(b"\xFF\xD8\xFF"):
            return "image/jpeg"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
            return "image/webp"
        if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
            return "image/gif"
        if data.startswith(b"BM"):
            return "image/bmp"
        return ""

    @staticmethod
    def _extract_mb_entity_id(data_url: str, entity: str) -> str:
        if not data_url:
            return ""
        match = re.search(rf"/{re.escape(entity)}/({_UUID_RE.pattern})", data_url)
        return match.group(1) if match else ""

    @staticmethod
    def _is_uuid(value: str) -> bool:
        return bool(value and _UUID_RE.fullmatch(value))
