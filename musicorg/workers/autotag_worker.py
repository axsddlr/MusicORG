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

    def run(self) -> None:
        self.started.emit()
        try:
            import re
            artist = self._artist_hint
            album = self._album_hint
            title = self._title_hint
            if self._regex_cleanup_pattern:
                try:
                    pat = re.compile(self._regex_cleanup_pattern)
                    artist = pat.sub(self._regex_cleanup_replacement, artist) if artist else artist
                    album = pat.sub(self._regex_cleanup_replacement, album) if album else album
                    title = pat.sub(self._regex_cleanup_replacement, title) if title else title
                except re.error:
                    pass

            auto_tagger = AutoTagger(
                discogs_token=self._discogs_token,
                enabled_sources=self._enabled_sources,
            )
            self.progress.emit(0, 1, "Searching...")
            search_payload: SearchDiagnostics
            if self._mode == "album":
                search_payload = auto_tagger.search_album_with_diagnostics(
                    self._paths,
                    artist_hint=self._artist_hint,
                    album_hint=self._album_hint,
                )
            else:
                if not self._paths:
                    self.finished.emit(
                        {"candidates": [], "source_errors": {}, "source_counts": {}}
                    )
                    return
                search_payload = auto_tagger.search_item_with_diagnostics(
                    self._paths[0],
                    artist_hint=self._artist_hint,
                    title_hint=self._title_hint,
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
        overwrite_fields: list[str] | None = None,
        fill_empty_only: bool = True,
    ) -> None:
        super().__init__()
        self._paths = [str(p) for p in paths]
        self._match = match
        self._cache_db_path = cache_db_path
        self._discogs_token = discogs_token
        self._overwrite_fields = overwrite_fields or []
        self._fill_empty_only = fill_empty_only

    def run(self) -> None:
        self.started.emit()
        try:
            auto_tagger = AutoTagger(discogs_token=self._discogs_token)
            self.progress.emit(0, 1, "Applying match...")
            if self._overwrite_fields:
                applied_successfully = auto_tagger.apply_match_with_overrides(
                    self._paths,
                    self._match,
                    overwrite_fields=self._overwrite_fields,
                    fill_empty_only=self._fill_empty_only,
                )
            else:
                applied_successfully = auto_tagger.apply_match(self._paths, self._match)
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
