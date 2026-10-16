"""Worker for querying MusicBrainz/Discogs metadata sources."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

from musicorg.core.autotagger import AutoTagger, SearchDiagnostics
from musicorg.core.tag_cache import TagCache
from musicorg.workers.base_worker import BaseWorker

if TYPE_CHECKING:
    from musicorg.core.autotagger import MatchCandidate


SearchMode = Literal["album", "single"]

ALL_FIELDS = ["title", "artist", "album", "albumartist", "track", "disc", "year", "genre", "artwork"]


class AutoTagWorker(BaseWorker):
    """Searches MusicBrainz/Discogs for matches in a background thread."""

    def __init__(
        self,
        paths: list[str | Path],
        artist_hint: str = "",
        album_hint: str = "",
        title_hint: str = "",
        mode: SearchMode = "album",
        discogs_token: str = "",
        enabled_sources: list[str] | None = None,
        regex_cleanup_pattern: str = "",
        regex_cleanup_replacement: str = "",
        duration_hint: int | None = None,
        isrc: str | None = None,
        max_distance: float | None = None,
    ) -> None:
        super().__init__()
        self._paths = [str(p) for p in paths]
        self._artist_hint = artist_hint
        self._album_hint = album_hint
        self._title_hint = title_hint
        self._mode = mode
        self._discogs_token = discogs_token
        self._enabled_sources = enabled_sources
        self._regex_cleanup_pattern = regex_cleanup_pattern
        self._regex_cleanup_replacement = regex_cleanup_replacement
        self._duration_hint = duration_hint
        self._isrc = isrc
        self._max_distance = max_distance

    def run(self) -> None:
        self.started.emit()
        try:
            import re
            artist = self._artist_hint
            album = self._album_hint
            title = self._title_hint
            regex_warning = ""
            if self._regex_cleanup_pattern:
                try:
                    pat = re.compile(self._regex_cleanup_pattern)
                    artist = pat.sub(self._regex_cleanup_replacement, artist) if artist else artist
                    album = pat.sub(self._regex_cleanup_replacement, album) if album else album
                    title = pat.sub(self._regex_cleanup_replacement, title) if title else title
                except re.error as exc:
                    regex_warning = f"Invalid cleanup regex: {exc}"

            auto_tagger = AutoTagger(
                discogs_token=self._discogs_token,
                enabled_sources=self._enabled_sources,
                max_distance=self._max_distance,
            )
            self.progress.emit(0, 1, regex_warning or "Searching...")
            search_payload: SearchDiagnostics
            if self._mode == "album":
                search_payload = auto_tagger.search_album_with_diagnostics(
                    self._paths,
                    artist_hint=artist,
                    album_hint=album,
                )
            else:
                if not self._paths:
                    self.finished.emit(
                        {"candidates": [], "source_errors": {}, "source_counts": {}}
                    )
                    return
                search_payload = auto_tagger.search_item_with_diagnostics(
                    self._paths[0],
                    artist_hint=artist,
                    title_hint=title,
                    duration_hint=self._duration_hint,
                    isrc=self._isrc,
                )
            candidates = search_payload.get("candidates", [])
            source_errors = search_payload.get("source_errors", {})
            if source_errors:
                unavailable = ", ".join(f"{name} unavailable" for name in source_errors)
                self.progress.emit(1, 1, f"Found {len(candidates)} candidates ({unavailable})")
            else:
                self.progress.emit(1, 1, f"Found {len(candidates)} candidates")
            self.finished.emit(search_payload)
        except Exception as exc:
            self.error.emit(str(exc))
        except BaseException as exc:
            # Catch SystemExit / KeyboardInterrupt so the UI is never left stuck
            self.error.emit(str(exc) or type(exc).__name__)
            raise


class ApplyMatchWorker(BaseWorker):
    """Applies a match to files in a background thread."""

    def __init__(
        self,
        paths: list[str | Path],
        match: MatchCandidate,
        *,
        cache_db_path: str = "",
        discogs_token: str = "",
        overwrite_fields: list[str] | None = None,  # None = all fields, [] = nothing
        fill_empty_only: bool = True,
        merge_genres: bool = False,
        id3_version: int = 4,
    ) -> None:
        super().__init__()
        self._paths = [str(p) for p in paths]
        self._match = match
        self._cache_db_path = cache_db_path
        self._discogs_token = discogs_token
        self._overwrite_fields = overwrite_fields
        self._fill_empty_only = fill_empty_only
        self._merge_genres = merge_genres
        self._id3_version = id3_version

    def run(self) -> None:
        self.started.emit()
        try:
            auto_tagger = AutoTagger(discogs_token=self._discogs_token)
            self.progress.emit(0, 1, "Applying match...")
            if self._overwrite_fields is None and not self._fill_empty_only:
                applied_successfully = auto_tagger.apply_match(
                    self._paths,
                    self._match,
                    merge_genres=self._merge_genres,
                    id3_version=self._id3_version,
                )
            else:
                fields = ALL_FIELDS if self._overwrite_fields is None else self._overwrite_fields
                applied_successfully = auto_tagger.apply_match_with_overrides(
                    self._paths,
                    self._match,
                    overwrite_fields=fields,
                    fill_empty_only=self._fill_empty_only,
                    merge_genres=self._merge_genres,
                    id3_version=self._id3_version,
                )
            if applied_successfully and self._cache_db_path:
                cache: TagCache | None = None
                try:
                    cache = TagCache(self._cache_db_path)
                    cache.open()
                    cache.invalidate_many(self._paths)
                except Exception:
                    pass
                finally:
                    if cache:
                        try:
                            cache.close()
                        except Exception:
                            pass
            self.progress.emit(1, 1, "Done")
            self.finished.emit(applied_successfully)
        except Exception as exc:
            self.error.emit(str(exc))
        except BaseException as exc:
            self.error.emit(str(exc) or type(exc).__name__)
            raise
