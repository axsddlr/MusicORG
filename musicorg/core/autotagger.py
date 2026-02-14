"""Direct MusicBrainz/Discogs lookup and tag application."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
import re
import time
from typing import Any, Callable, ParamSpec, TypeVar, TypedDict
from urllib.request import Request, urlopen

from musicorg import __version__
from musicorg.core.tagger import TagData, TagManager


_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

P = ParamSpec("P")
R = TypeVar("R")


class TrackMetadata(TypedDict):
    track: int
    disc: int
    title: str
    artist: str
    length: int


class MatchPayload(TypedDict, total=False):
    source: str
    artist: str
    album: str
    year: int
    release_id: str
    release_group_id: str
    tracks: list[TrackMetadata]
    artwork_urls: list[str]
    genre: str
    track: int
    disc: int
    title: str
    length: int


class SearchDiagnostics(TypedDict):
    candidates: list["MatchCandidate"]
    source_errors: dict[str, str]
    source_counts: dict[str, int]


@dataclass
class MatchCandidate:
    """A single match candidate from MusicBrainz or Discogs."""

    source: str = ""  # "MusicBrainz" or "Discogs"
    artist: str = ""
    album: str = ""
    year: int = 0
    distance: float = 1.0  # 0.0 = perfect, 1.0 = worst
    tracks: list[TrackMetadata] = field(default_factory=list)
    raw_match: MatchPayload | None = None

    @property
    def match_percent(self) -> float:
        return round((1.0 - self.distance) * 100, 1)


class AutoTagger:
    """Searches direct metadata providers and writes tags from selected match."""

    _mb_useragent_set = False

    def __init__(self, discogs_token: str = "") -> None:
        self._discogs_token = discogs_token.strip()
        if not AutoTagger._mb_useragent_set:
            try:
                import musicbrainzngs

                musicbrainzngs.set_useragent("MusicOrg", __version__, "https://musicbrainz.org")
                AutoTagger._mb_useragent_set = True
            except Exception:
                # Defer import/setup errors to search methods.
                pass

    def search_album(
        self,
        paths: list[str | Path],
        artist_hint: str = "",
        album_hint: str = "",
    ) -> list[MatchCandidate]:
        """Search MusicBrainz and Discogs for album matches."""
        payload = self.search_album_with_diagnostics(
            paths=paths,
            artist_hint=artist_hint,
            album_hint=album_hint,
        )
        return payload["candidates"]

    def search_album_with_diagnostics(
        self,
        paths: list[str | Path],
        artist_hint: str = "",
        album_hint: str = "",
    ) -> SearchDiagnostics:
        """Search album matches with per-source diagnostics."""
        if not paths:
            return self._build_search_payload([], {})
        artist, album = self._resolve_hints_from_files(paths, artist_hint, album_hint)
        if not artist and not album:
            return self._build_search_payload([], {})

        results: list[MatchCandidate] = []
        source_errors: dict[str, str] = {}
        attempted_sources: list[str] = []

        attempted_sources.append("MusicBrainz")
        try:
            results.extend(self._call_with_retry(self._search_album_mb, artist, album))
        except Exception as exc:
            source_errors["MusicBrainz"] = str(exc)

        if self._discogs_token:
            attempted_sources.append("Discogs")
            try:
                results.extend(self._call_with_retry(self._search_album_discogs, artist, album))
            except Exception as exc:
                source_errors["Discogs"] = str(exc)

        results.sort(key=lambda m: m.distance)
        if not results and attempted_sources and len(source_errors) == len(attempted_sources):
            detail = "; ".join(
                f"{source}: {source_errors[source]}"
                for source in attempted_sources
                if source in source_errors
            )
            raise RuntimeError(detail)
        return self._build_search_payload(results, source_errors)

    def search_item(
        self,
        path: str | Path,
        artist_hint: str = "",
        title_hint: str = "",
    ) -> list[MatchCandidate]:
        """Search MusicBrainz and Discogs for single-track matches."""
        payload = self.search_item_with_diagnostics(
            path=path,
            artist_hint=artist_hint,
            title_hint=title_hint,
        )
        return payload["candidates"]

    def search_item_with_diagnostics(
        self,
        path: str | Path,
        artist_hint: str = "",
        title_hint: str = "",
    ) -> SearchDiagnostics:
        """Search single-track matches with per-source diagnostics."""
        path = Path(path)
        if not path.exists():
            return self._build_search_payload([], {})

        artist = artist_hint.strip()
        title = title_hint.strip()
        if not artist or not title:
            tm = TagManager()
            try:
                tags = tm.read(path)
                if not artist:
                    artist = (tags.artist or tags.albumartist or "").strip()
                if not title:
                    title = (tags.title or "").strip()
            except Exception:
                pass
        if not artist and not title:
            return self._build_search_payload([], {})

        results: list[MatchCandidate] = []
        source_errors: dict[str, str] = {}
        attempted_sources: list[str] = []

        attempted_sources.append("MusicBrainz")
        try:
            results.extend(self._call_with_retry(self._search_item_mb, artist, title))
        except Exception as exc:
            source_errors["MusicBrainz"] = str(exc)

        if self._discogs_token:
            attempted_sources.append("Discogs")
            try:
                results.extend(self._call_with_retry(self._search_item_discogs, artist, title))
            except Exception as exc:
                source_errors["Discogs"] = str(exc)

        results.sort(key=lambda m: m.distance)
        if not results and attempted_sources and len(source_errors) == len(attempted_sources):
            detail = "; ".join(
                f"{source}: {source_errors[source]}"
                for source in attempted_sources
                if source in source_errors
            )
            raise RuntimeError(detail)
        return self._build_search_payload(results, source_errors)

    def apply_match(self, paths: list[str | Path], match: MatchCandidate) -> bool:
        """Apply a selected dict-based match candidate to one or more files."""
        if not paths:
            return False
        match_payload = getattr(match, "raw_match", None)
        if not isinstance(match_payload, dict):
            return False

        try:
            artwork = self._download_artwork_from_urls(match_payload.get("artwork_urls", []))
            artwork_data = artwork[0] if artwork else None
            artwork_mime = artwork[1] if artwork else ""

            tag_writer = TagManager()
            if isinstance(match_payload.get("tracks"), list):
                return self._apply_album_match(
                    tag_writer=tag_writer,
                    paths=paths,
                    match_payload=match_payload,
                    artwork_data=artwork_data,
                    artwork_mime=artwork_mime,
                )
            return self._apply_single_match(
                tag_writer=tag_writer,
                paths=paths,
                match_payload=match_payload,
                artwork_data=artwork_data,
                artwork_mime=artwork_mime,
            )
        except Exception as exc:
            raise RuntimeError(f"Apply match failed: {exc}") from exc

    def _resolve_hints_from_files(
        self,
        paths: list[str | Path],
        artist_hint: str,
        album_hint: str,
    ) -> tuple[str, str]:
        artist = artist_hint.strip()
        album = album_hint.strip()
        if artist and album:
            return artist, album

        tm = TagManager()
        for raw_path in paths:
            try:
                tags = tm.read(raw_path)
            except Exception:
                continue
            if not artist:
                artist = (tags.albumartist or tags.artist or "").strip()
            if not album:
                album = (tags.album or "").strip()
            if artist and album:
                break
        return artist, album

    def _search_album_mb(self, artist: str, album: str) -> list[MatchCandidate]:
        import musicbrainzngs

        query: dict[str, Any] = {"limit": 5}
        if artist:
            query["artist"] = artist
        if album:
            query["release"] = album
        data = musicbrainzngs.search_releases(**query)

        candidates: list[MatchCandidate] = []
        for release in data.get("release-list", [])[:5]:
            release_id = str(release.get("id", "") or "")
            full_release = release
            if self._is_uuid(release_id):
                try:
                    details = musicbrainzngs.get_release_by_id(
                        release_id,
                        includes=["recordings", "artist-credits"],
                    )
                    full_release = details.get("release", release)
                except Exception:
                    pass

            release_group = full_release.get("release-group") or release.get("release-group") or {}
            release_group_id = str(release_group.get("id", "") or "")
            track_rows = self._mb_album_tracks(full_release)
            artist_name = self._mb_artist_credit(full_release) or self._mb_artist_credit(release)
            title = str(full_release.get("title", "") or release.get("title", ""))
            year = self._mb_extract_year(full_release) or self._mb_extract_year(release)
            score = float(release.get("ext:score", 0) or 0.0)
            distance = 1.0 - max(0.0, min(score, 100.0)) / 100.0

            raw_match: MatchPayload = {
                "source": "MusicBrainz",
                "artist": artist_name,
                "album": title,
                "year": year,
                "release_id": release_id,
                "release_group_id": release_group_id,
                "tracks": track_rows,
                "artwork_urls": self._mb_artwork_urls(release_id, release_group_id),
                "genre": "",
            }
            candidates.append(
                MatchCandidate(
                    source="MusicBrainz",
                    artist=artist_name,
                    album=title,
                    year=year,
                    distance=distance,
                    tracks=track_rows,
                    raw_match=raw_match,
                )
            )
        return candidates

    def _mb_album_tracks(self, release: dict[str, Any]) -> list[TrackMetadata]:
        tracks: list[TrackMetadata] = []
        medium_list = release.get("medium-list", [])
        for medium_index, medium in enumerate(medium_list, start=1):
            disc_num = self._coerce_int(medium.get("position", medium_index), medium_index)
            for track_index, track in enumerate(medium.get("track-list", []), start=1):
                recording = track.get("recording", {})
                title = str(recording.get("title", "") or track.get("title", ""))
                track_artist = self._mb_artist_credit(recording) or self._mb_artist_credit(track)
                length_ms = recording.get("length", track.get("length", 0))
                length_secs = int(length_ms) // 1000 if str(length_ms).isdigit() else 0
                track_num = self._coerce_int(
                    track.get("number", track.get("position", track_index)),
                    track_index,
                )
                tracks.append(
                    {
                        "track": track_num,
                        "disc": disc_num,
                        "title": title,
                        "artist": track_artist,
                        "length": length_secs,
                    }
                )
        return tracks

    def _search_album_discogs(self, artist: str, album: str) -> list[MatchCandidate]:
        import discogs_client

        query: dict[str, Any] = {"type": "release"}
        if artist:
            query["artist"] = artist
        if album:
            query["release_title"] = album

        client = discogs_client.Client("MusicOrg/" + __version__, user_token=self._discogs_token)
        releases = client.search(**query)

        candidates: list[MatchCandidate] = []
        for release in self._limit_results(releases, 5):
            release_artist = self._discogs_artist_name(release)
            release_album = str(getattr(release, "title", "") or "")
            release_year = self._coerce_int(getattr(release, "year", 0), 0)
            release_id = str(getattr(release, "id", "") or "")
            track_rows = self._discogs_tracks(release)
            artwork_urls = self._discogs_artwork_urls(release)
            genre = ", ".join(
                part
                for part in [*list(getattr(release, "genres", []) or []), *list(getattr(release, "styles", []) or [])]
                if part
            )
            distance = self._discogs_distance(artist, album, release)

            raw_match: MatchPayload = {
                "source": "Discogs",
                "artist": release_artist,
                "album": release_album,
                "year": release_year,
                "release_id": release_id,
                "release_group_id": "",
                "tracks": track_rows,
                "artwork_urls": artwork_urls,
                "genre": genre,
            }
            candidates.append(
                MatchCandidate(
                    source="Discogs",
                    artist=release_artist,
                    album=release_album,
                    year=release_year,
                    distance=distance,
                    tracks=track_rows,
                    raw_match=raw_match,
                )
            )
        return candidates

    def _discogs_tracks(self, release: Any) -> list[TrackMetadata]:
        track_rows: list[TrackMetadata] = []
        tracklist = list(getattr(release, "tracklist", []) or [])
        for index, track in enumerate(tracklist, start=1):
            disc_num, track_num = self._parse_discogs_position(
                str(getattr(track, "position", "") or ""),
                default_disc=1,
            )
            if track_num <= 0:
                track_num = index
            track_rows.append(
                {
                    "track": track_num,
                    "disc": disc_num,
                    "title": str(getattr(track, "title", "") or ""),
                    "artist": self._discogs_artist_name(release),
                    "length": self._parse_duration(str(getattr(track, "duration", "") or "")),
                }
            )
        return track_rows

    def _search_item_mb(self, artist: str, title: str) -> list[MatchCandidate]:
        import musicbrainzngs

        query: dict[str, Any] = {"limit": 10}
        if artist:
            query["artist"] = artist
        if title:
            query["recording"] = title
        data = musicbrainzngs.search_recordings(**query)

        candidates: list[MatchCandidate] = []
        for recording in data.get("recording-list", [])[:10]:
            release = (recording.get("release-list") or [{}])[0]
            release_id = str(release.get("id", "") or "")
            release_group = release.get("release-group") or {}
            release_group_id = str(release_group.get("id", "") or "")
            item_artist = self._mb_artist_credit(recording) or artist
            item_title = str(recording.get("title", "") or title)
            item_album = str(release.get("title", "") or "")
            item_year = self._mb_extract_year(release)
            score = float(recording.get("ext:score", 0) or 0.0)
            distance = 1.0 - max(0.0, min(score, 100.0)) / 100.0
            length_ms = recording.get("length", 0)
            length_secs = int(length_ms) // 1000 if str(length_ms).isdigit() else 0

            raw_match: MatchPayload = {
                "source": "MusicBrainz",
                "artist": item_artist,
                "album": item_album,
                "year": item_year,
                "release_id": release_id,
                "release_group_id": release_group_id,
                "track": 0,
                "disc": 0,
                "title": item_title,
                "length": length_secs,
                "artwork_urls": self._mb_artwork_urls(release_id, release_group_id),
                "genre": "",
            }
            candidates.append(
                MatchCandidate(
                    source="MusicBrainz",
                    artist=item_artist,
                    album=item_album,
                    year=item_year,
                    distance=distance,
                    tracks=[
                        {
                            "track": 0,
                            "disc": 0,
                            "title": item_title,
                            "artist": item_artist,
                            "length": length_secs,
                        }
                    ],
                    raw_match=raw_match,
                )
            )
        return candidates

    def _search_item_discogs(self, artist: str, title: str) -> list[MatchCandidate]:
        import discogs_client

        if not title:
            return []

        client = discogs_client.Client("MusicOrg/" + __version__, user_token=self._discogs_token)
        releases = client.search(title, type="release")

        candidates: list[MatchCandidate] = []
        for release in self._limit_results(releases, 25):
            best_track = None
            best_ratio = 0.0
            for track in list(getattr(release, "tracklist", []) or []):
                track_title = str(getattr(track, "title", "") or "")
                if not track_title:
                    continue
                ratio = SequenceMatcher(None, title.lower(), track_title.lower()).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_track = track
            if best_track is None or best_ratio < 0.6:
                continue

            disc_num, track_num = self._parse_discogs_position(
                str(getattr(best_track, "position", "") or ""),
                default_disc=1,
            )
            release_artist = self._discogs_artist_name(release)
            release_album = str(getattr(release, "title", "") or "")
            release_year = self._coerce_int(getattr(release, "year", 0), 0)
            release_id = str(getattr(release, "id", "") or "")
            artwork_urls = self._discogs_artwork_urls(release)
            genre = ", ".join(
                part
                for part in [*list(getattr(release, "genres", []) or []), *list(getattr(release, "styles", []) or [])]
                if part
            )
            release_distance = self._discogs_distance(artist, release_album, release)
            title_distance = 1.0 - best_ratio
            distance = max(0.0, min(1.0, (release_distance * 0.4) + (title_distance * 0.6)))
            matched_title = str(getattr(best_track, "title", "") or "")
            length = self._parse_duration(str(getattr(best_track, "duration", "") or ""))

            raw_match: MatchPayload = {
                "source": "Discogs",
                "artist": release_artist,
                "album": release_album,
                "year": release_year,
                "release_id": release_id,
                "release_group_id": "",
                "track": track_num,
                "disc": disc_num,
                "title": matched_title,
                "length": length,
                "artwork_urls": artwork_urls,
                "genre": genre,
            }
            candidates.append(
                MatchCandidate(
                    source="Discogs",
                    artist=release_artist,
                    album=release_album,
                    year=release_year,
                    distance=distance,
                    tracks=[
                        {
                            "track": track_num,
                            "disc": disc_num,
                            "title": matched_title,
                            "artist": release_artist,
                            "length": length,
                        }
                    ],
                    raw_match=raw_match,
                )
            )
            if len(candidates) >= 5:
                break
        return candidates

    def _apply_album_match(
        self,
        tag_writer: TagManager,
        paths: list[str | Path],
        match_payload: MatchPayload,
        artwork_data: bytes | None,
        artwork_mime: str,
    ) -> bool:
        file_rows: list[tuple[int, int, int, Path]] = []
        for index, path in enumerate(paths):
            path_obj = Path(path)
            disc = 1
            track = index + 1
            try:
                tags = tag_writer.read(path_obj)
                if tags.disc > 0:
                    disc = tags.disc
                if tags.track > 0:
                    track = tags.track
            except Exception:
                pass
            file_rows.append((disc, track, index, path_obj))
        file_rows.sort(key=lambda row: (row[0], row[1], row[2]))

        tracks = list(match_payload.get("tracks") or [])
        tracks.sort(key=lambda row: (self._coerce_int(row.get("disc"), 1), self._coerce_int(row.get("track"), 0)))
        if not tracks:
            return False

        album_artist = str(match_payload.get("artist", "") or "")
        album = str(match_payload.get("album", "") or "")
        year = self._coerce_int(match_payload.get("year", 0), 0)
        genre = str(match_payload.get("genre", "") or "")

        for index, (_, _, _, path_obj) in enumerate(file_rows):
            track_row = tracks[index] if index < len(tracks) else tracks[-1]
            tag_data = TagData(
                title=str(track_row.get("title", "") or ""),
                artist=str(track_row.get("artist", "") or album_artist),
                album=album,
                albumartist=album_artist,
                track=self._coerce_int(track_row.get("track"), index + 1),
                disc=self._coerce_int(track_row.get("disc"), 1),
                year=year,
                genre=genre,
                artwork_data=artwork_data,
                artwork_mime=artwork_mime,
            )
            tag_writer.write(path_obj, tag_data)
        return True

    def _apply_single_match(
        self,
        tag_writer: TagManager,
        paths: list[str | Path],
        match_payload: MatchPayload,
        artwork_data: bytes | None,
        artwork_mime: str,
    ) -> bool:
        artist = str(match_payload.get("artist", "") or "")
        album = str(match_payload.get("album", "") or "")
        title = str(match_payload.get("title", "") or "")
        year = self._coerce_int(match_payload.get("year", 0), 0)
        genre = str(match_payload.get("genre", "") or "")
        track = self._coerce_int(match_payload.get("track", 0), 0)
        disc = self._coerce_int(match_payload.get("disc", 0), 0)
        tag_data = TagData(
            title=title,
            artist=artist,
            album=album,
            albumartist=artist,
            track=track,
            disc=disc,
            year=year,
            genre=genre,
            artwork_data=artwork_data,
            artwork_mime=artwork_mime,
        )
        for path in paths:
            tag_writer.write(path, tag_data)
        return True

    @staticmethod
    def _mb_artist_credit(entity: dict[str, Any]) -> str:
        artist_credit = entity.get("artist-credit")
        if not artist_credit:
            phrase = entity.get("artist-credit-phrase")
            return str(phrase or "")
        parts: list[str] = []
        for chunk in artist_credit:
            if isinstance(chunk, str):
                parts.append(chunk)
                continue
            if isinstance(chunk, dict):
                name = chunk.get("name")
                if not name:
                    artist = chunk.get("artist") or {}
                    name = artist.get("name")
                if name:
                    parts.append(str(name))
                joinphrase = chunk.get("joinphrase")
                if joinphrase:
                    parts.append(str(joinphrase))
        return "".join(parts).strip()

    @staticmethod
    def _mb_extract_year(release: dict[str, Any]) -> int:
        if not isinstance(release, dict):
            return 0
        for key in ("date", "first-release-date"):
            date_raw = str(release.get(key, "") or "")
            match = re.match(r"^(\d{4})", date_raw)
            if match:
                return int(match.group(1))
        return 0

    @classmethod
    def _mb_artwork_urls(cls, release_id: str, release_group_id: str) -> list[str]:
        urls: list[str] = []
        if cls._is_uuid(release_id):
            urls.extend(
                [
                    f"https://coverartarchive.org/release/{release_id}/front-500",
                    f"https://coverartarchive.org/release/{release_id}/front",
                ]
            )
        if cls._is_uuid(release_group_id):
            urls.extend(
                [
                    f"https://coverartarchive.org/release-group/{release_group_id}/front-500",
                    f"https://coverartarchive.org/release-group/{release_group_id}/front",
                ]
            )
        return cls._dedupe_urls(urls)

    @classmethod
    def _discogs_artwork_urls(cls, release: Any) -> list[str]:
        urls: list[str] = []
        images = list(getattr(release, "images", None) or [])
        for image in images:
            if not isinstance(image, dict):
                continue
            # Discogs image payloads commonly expose both URI variants.
            for key in ("uri150", "uri"):
                value = str(image.get(key, "") or "").strip()
                if value:
                    urls.append(value)
        return cls._dedupe_urls(urls)

    @staticmethod
    def _discogs_distance(query_artist: str, query_album: str, release: Any) -> float:
        release_artist = AutoTagger._discogs_artist_name(release)
        release_title = str(getattr(release, "title", "") or "")
        query_artist = query_artist.strip().lower()
        query_album = query_album.strip().lower()
        release_artist = release_artist.strip().lower()
        release_title = release_title.strip().lower()

        if not query_artist and not query_album:
            return 1.0

        artist_weight = 0.4 if query_artist else 0.0
        album_weight = 0.6 if query_album else 0.0
        total = artist_weight + album_weight
        if total <= 0.0:
            return 1.0

        artist_ratio = SequenceMatcher(None, query_artist, release_artist).ratio() if query_artist else 0.0
        album_ratio = SequenceMatcher(None, query_album, release_title).ratio() if query_album else 0.0
        weighted = ((artist_ratio * artist_weight) + (album_ratio * album_weight)) / total
        return max(0.0, min(1.0, 1.0 - weighted))

    @staticmethod
    def _parse_duration(duration: str) -> int:
        duration = duration.strip()
        if not duration:
            return 0
        if duration.isdigit():
            return int(duration)
        parts = duration.split(":")
        if not parts or any(not part.isdigit() for part in parts):
            return 0
        value = 0
        for part in parts:
            value = (value * 60) + int(part)
        return value

    @staticmethod
    def _parse_discogs_position(position: str, default_disc: int = 1) -> tuple[int, int]:
        position = position.strip().upper()
        if not position:
            return default_disc, 0

        match = re.match(r"^(\d+)-(\d+)$", position)
        if match:
            return int(match.group(1)), int(match.group(2))

        match = re.match(r"^([A-Z])(\d+)$", position)
        if match:
            disc_num = ord(match.group(1)) - ord("A") + 1
            return max(1, disc_num), int(match.group(2))

        match = re.match(r"^\d+$", position)
        if match:
            return default_disc, int(position)

        # Fallback: pick first integer from mixed strings like "CD1-03" or "Track 4".
        match = re.search(r"(\d+)", position)
        if match:
            return default_disc, int(match.group(1))
        return default_disc, 0

    @classmethod
    def _download_artwork_from_urls(cls, urls: list[str]) -> tuple[bytes, str] | None:
        candidates = cls._expand_artwork_urls(urls)
        for url in candidates:
            if not url:
                continue
            for attempt in range(3):
                try:
                    req = Request(
                        url,
                        headers={
                            "User-Agent": f"MusicOrg/{__version__}",
                            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                            "Referer": "https://musicbrainz.org/",
                        },
                    )
                    with urlopen(req, timeout=12) as resp:
                        data = resp.read()
                        if not data:
                            break
                        mime = cls._normalize_content_type(resp.headers.get("Content-Type", ""))
                        guessed_mime = cls._guess_image_mime(data)
                        if not mime:
                            mime = guessed_mime
                        # Skip obvious HTML/error payloads misreported as binary.
                        if not mime and cls._looks_like_html(data):
                            break
                        if not mime:
                            mime = "image/jpeg"
                        return data, mime
                except Exception as exc:
                    if attempt >= 2 or not cls._is_transient_network_error(exc):
                        break
                    time.sleep(0.25 * (attempt + 1))
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
    def _looks_like_html(data: bytes) -> bool:
        snippet = data[:256].lstrip().lower()
        return snippet.startswith(b"<!doctype html") or snippet.startswith(b"<html")

    @classmethod
    def _expand_artwork_urls(cls, urls: list[str]) -> list[str]:
        expanded: list[str] = []
        for raw in urls:
            url = str(raw or "").strip()
            if not url:
                continue
            expanded.append(url)
            https_url = ""
            if url.startswith("http://"):
                https_url = "https://" + url[len("http://"):]
                expanded.append(https_url)
            if "coverartarchive.org" in url and "/front-500" in url:
                expanded.append(url.replace("/front-500", "/front"))
                if https_url:
                    expanded.append(https_url.replace("/front-500", "/front"))
        return cls._dedupe_urls(expanded)

    def _call_with_retry(
        self,
        operation: Callable[P, R],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return operation(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                if attempt >= 2 or not self._is_transient_network_error(exc):
                    raise
                time.sleep(0.35 * (attempt + 1))
        if last_error is not None:
            raise last_error
        raise RuntimeError("retry wrapper reached an unexpected state")

    @staticmethod
    def _dedupe_urls(urls: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for url in urls:
            normalized = str(url or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    @staticmethod
    def _is_transient_network_error(exc: Exception) -> bool:
        text = " ".join(str(exc).lower().split())
        transient_markers = (
            "timed out",
            "timeout",
            "forcibly closed",
            "connection reset",
            "remote end closed",
            "temporarily unavailable",
            "try again",
            "service unavailable",
            "winerror 10054",
            "http error 429",
            "http error 502",
            "http error 503",
            "http error 504",
        )
        return any(marker in text for marker in transient_markers)

    @staticmethod
    def _discogs_artist_name(release: Any) -> str:
        artists = list(getattr(release, "artists", []) or [])
        names = [str(getattr(artist, "name", "") or "").strip() for artist in artists]
        names = [name for name in names if name]
        if names:
            return ", ".join(names)
        return str(getattr(release, "artist", "") or "")

    @staticmethod
    def _coerce_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _limit_results(results: Any, limit: int) -> list[Any]:
        output: list[Any] = []
        for item in results:
            output.append(item)
            if len(output) >= limit:
                break
        return output

    @staticmethod
    def _is_uuid(value: str) -> bool:
        return bool(value and _UUID_RE.fullmatch(value))

    @staticmethod
    def _build_search_payload(
        candidates: list[MatchCandidate],
        source_errors: dict[str, str],
    ) -> SearchDiagnostics:
        source_counts: dict[str, int] = {"MusicBrainz": 0, "Discogs": 0}
        for candidate in candidates:
            if candidate.source in source_counts:
                source_counts[candidate.source] += 1
        return {
            "candidates": candidates,
            "source_errors": source_errors,
            "source_counts": source_counts,
        }
