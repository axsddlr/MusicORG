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
    ) -> None:
        super().__init__()
        self._paths = [str(p) for p in paths]
        self._artist_hint = artist_hint
        self._album_hint = album_hint
        self._title_hint = title_hint
        self._mode = mode
        self._discogs_token = discogs_token

    def run(self) -> None:
        self.started.emit()
        try:
            auto_tagger = AutoTagger(discogs_token=self._discogs_token)
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


class ApplyMatchWorker(BaseWorker):
    """Applies a match to files in a background thread."""

    def __init__(
        self,
        paths: list[str | Path],
        match: MatchCandidate,
        *,
        cache_db_path: str = "",
        discogs_token: str = "",
    ) -> None:
        super().__init__()
        self._paths = [str(p) for p in paths]
        self._match = match
        self._cache_db_path = cache_db_path
        self._discogs_token = discogs_token

    def run(self) -> None:
        self.started.emit()
        try:
            auto_tagger = AutoTagger(discogs_token=self._discogs_token)
            self.progress.emit(0, 1, "Applying match...")
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
