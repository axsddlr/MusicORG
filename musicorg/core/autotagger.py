"""MusicBrainz/Discogs lookup via beets autotag API."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
        try:
            return self._search_album_beets(paths, artist_hint, album_hint)
        except Exception:
            return []

    def search_item(self, path: str | Path,
                    artist_hint: str = "",
                    title_hint: str = "") -> list[MatchCandidate]:
        """Search for single-track matches."""
        try:
            return self._search_item_beets(path, artist_hint, title_hint)
        except Exception:
            return []

    def apply_match(self, paths: list[str | Path],
                    match: MatchCandidate) -> bool:
        """Apply a match's metadata to the files."""
        try:
            return self._apply_match_beets(paths, match)
        except Exception:
            return False

    # -- beets implementation --

    def _search_album_beets(self, paths, artist_hint, album_hint):
        from beets import autotag
        from beets.library import Item

        items = []
        for p in paths:
            item = Item.from_path(str(p))
            item.read()
            items.append(item)

        artist = artist_hint or items[0].albumartist or items[0].artist or ""
        album = album_hint or items[0].album or ""

        try:
            candidates_iter = autotag.match.tag_album(items, artist, album)
            # tag_album returns (artist, album, candidates, recommendation)
            # or an iterator of AlbumMatch in newer versions
            if hasattr(candidates_iter, '__iter__') and not isinstance(candidates_iter, tuple):
                candidates = list(candidates_iter)
            else:
                _, _, candidates, _ = candidates_iter
                candidates = list(candidates)
        except Exception:
            return []

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

        try:
            candidates_iter = autotag.match.tag_item(item, artist, title)
            if hasattr(candidates_iter, '__iter__'):
                candidates = list(candidates_iter)
            else:
                candidates = [candidates_iter]
        except Exception:
            return []

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

        # Apply metadata from the match to the items
        try:
            # Try album-level apply
            mapping = getattr(raw, 'mapping', None)
            if mapping:
                autotag.apply.apply_metadata(info, mapping)
            else:
                # Direct apply for each item
                track_infos = getattr(info, 'tracks', [])
                for item, ti in zip(items, track_infos):
                    autotag.apply.apply_item_metadata(item, ti)
        except (AttributeError, TypeError):
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
            )
            tm.write(item.path if isinstance(item.path, (str, Path)) else item.path.decode(), td)

        return True
