"""Search Traxsource for track/album metadata by web scraping."""

from __future__ import annotations

import re
import time
from difflib import SequenceMatcher
from typing import Any
from urllib.request import Request, urlopen

from musicorg import __version__

TRAXSOURCE_SEARCH_URL = "https://www.traxsource.com/search?term="


class TraxsourceClient:
    """Scrapes Traxsource for track and release metadata."""

    _CACHE_TTL = 3600

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, list[dict]]] = {}

    def search_album(
        self, artist: str, album: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        cache_key = f"a:{artist.lower()}|{album.lower()}"
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached[0]) < self._CACHE_TTL:
            return cached[1][:limit]

        query = f"{artist} {album}"
        results = self._search_tracks(query)
        candidates = self._deduplicate_by_release(results, limit)
        self._cache[cache_key] = (time.time(), candidates)
        return candidates[:limit]

    def search_item(
        self, artist: str, title: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        cache_key = f"t:{artist.lower()}|{title.lower()}"
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached[0]) < self._CACHE_TTL:
            return cached[1][:limit]

        query = f"{artist} {title}"
        results = self._search_tracks(query)
        scored = []
        for trk in results:
            t_artist = str(trk.get("artist", "") or "")
            t_title = str(trk.get("title", "") or "")
            ar = (
                SequenceMatcher(None, artist.lower(), t_artist.lower()).ratio()
                if artist
                else 0.0
            )
            tr = (
                SequenceMatcher(None, title.lower(), t_title.lower()).ratio()
                if title
                else 0.0
            )
            w = 0.0
            if artist:
                w += 0.4
            if title:
                w += 0.6
            score = ((ar * 0.4) + (tr * 0.6)) / w if w > 0 else 0.0
            trk["_score"] = score
            scored.append(trk)
        scored.sort(key=lambda t: t.get("_score", 0), reverse=True)
        self._cache[cache_key] = (time.time(), scored)
        return scored[:limit]

    def _search_tracks(self, query: str) -> list[dict[str, Any]]:
        import urllib.parse
        from bs4 import BeautifulSoup

        url = TRAXSOURCE_SEARCH_URL + urllib.parse.quote(query)
        req = Request(
            url,
            headers={
                "User-Agent": f"MusicOrg/{__version__}",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        results: list[dict[str, Any]] = []
        try:
            with urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                soup = BeautifulSoup(html, "html.parser")
                items = soup.select("div.trk-row")
                for item in items[:10]:
                    track = self._parse_track_row(item)
                    if track:
                        results.append(track)
        except Exception:
            pass
        return results

    def _parse_track_row(self, item: Any) -> dict[str, Any] | None:
        title_el = item.select_one(".title a, .trk-cell.title a")
        artist_el = item.select_one(".artists a, .trk-cell.artists a")
        label_el = item.select_one(".label a, .trk-cell.label a")
        genre_el = item.select_one(".genre a, .trk-cell.genre a")
        release_el = item.select_one(".release a, .trk-cell.release a")
        length_el = item.select_one(".time, .trk-cell.time")
        img_el = item.select_one("img")

        title = (title_el.text or "").strip() if title_el else ""
        artist = (artist_el.text or "").strip() if artist_el else ""
        label = (label_el.text or "").strip() if label_el else ""
        genre = (genre_el.text or "").strip() if genre_el else ""
        release = (release_el.text or "").strip() if release_el else ""
        length_raw = (length_el.text or "").strip() if length_el else ""
        cover = ""
        if img_el:
            cover = str(img_el.get("src", "") or img_el.get("data-src", "") or "")

        return {
            "title": title,
            "artist": artist,
            "release": release,
            "label": label,
            "genre": genre,
            "length": length_raw,
            "cover_url": cover,
            "source": "Traxsource",
        }

    def _deduplicate_by_release(
        self, tracks: list[dict[str, Any]], limit: int
    ) -> list[dict[str, Any]]:
        seen: set[str] = set()
        grouped: dict[str, list[dict]] = {}
        order: list[str] = []
        for trk in tracks:
            rel = (trk.get("release", "") or "").lower()
            if rel not in seen:
                seen.add(rel)
                order.append(rel)
                grouped[rel] = []
            grouped[rel].append(trk)
        candidates: list[dict[str, Any]] = []
        for rel in order:
            items = grouped[rel]
            artist = ", ".join(
                sorted(set(t.get("artist", "") for t in items if t.get("artist")))
            )
            genres = [t.get("genre", "") for t in items if t.get("genre")]
            genre = ", ".join(sorted(set(g for g in genres if g)))
            label = items[0].get("label", "")
            cover = items[0].get("cover_url", "")
            candidates.append({
                "source": "Traxsource",
                "artist": artist,
                "album": items[0].get("release", ""),
                "label": label,
                "genre": genre,
                "artwork_urls": [cover] if cover else [],
                "tracks": [
                    {"track": i + 1, "disc": 1, "title": t.get("title", ""),
                     "artist": t.get("artist", artist), "length": 0}
                    for i, t in enumerate(items)
                ],
            })
            if len(candidates) >= limit:
                break
        return candidates
