"""Worker for querying MusicBrainz/Discogs via beets autotag."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from musicorg.core.autotagger import AutoTagger
from musicorg.workers.base_worker import BaseWorker

if TYPE_CHECKING:
    from musicorg.core.autotagger import MatchCandidate


class AutoTagWorker(BaseWorker):
    """Searches MusicBrainz/Discogs for matches in a background thread."""

    def __init__(self, paths: list[str | Path],
                 artist_hint: str = "",
                 album_hint: str = "",
                 mode: str = "album") -> None:
        super().__init__()
        self._paths = [str(p) for p in paths]
        self._artist_hint = artist_hint
        self._album_hint = album_hint
        self._mode = mode

    def run(self) -> None:
        self.started.emit()
        try:
            tagger = AutoTagger()
            self.progress.emit(0, 1, "Searching...")
            if self._mode == "album":
                results = tagger.search_album(
                    self._paths,
                    artist_hint=self._artist_hint,
                    album_hint=self._album_hint,
                )
            else:
                results = tagger.search_item(
                    self._paths[0],
                    artist_hint=self._artist_hint,
                    title_hint=self._album_hint,
                )
            self.progress.emit(1, 1, f"Found {len(results)} candidates")
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class ApplyMatchWorker(BaseWorker):
    """Applies a match to files in a background thread."""

    def __init__(self, paths: list[str | Path], match: MatchCandidate) -> None:
        super().__init__()
        self._paths = [str(p) for p in paths]
        self._match = match

    def run(self) -> None:
        self.started.emit()
        try:
            tagger = AutoTagger()
            self.progress.emit(0, 1, "Applying match...")
            success = tagger.apply_match(self._paths, self._match)
            self.progress.emit(1, 1, "Done")
            self.finished.emit(success)
        except Exception as e:
            self.error.emit(str(e))
