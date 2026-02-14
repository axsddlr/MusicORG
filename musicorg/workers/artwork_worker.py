"""Workers for artwork search and preview download."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from musicorg.core.autotagger import AutoTagger
from musicorg.workers.base_worker import BaseWorker

if TYPE_CHECKING:
    from musicorg.core.autotagger import MatchCandidate


class ArtworkSearchWorker(BaseWorker):
    """Searches metadata providers for artwork-capable match candidates."""

    def __init__(
        self,
        *,
        paths: list[str | Path],
        artist_hint: str = "",
        album_hint: str = "",
        title_hint: str = "",
        mode: str = "album",
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
            tagger = AutoTagger(discogs_token=self._discogs_token)
            self.progress.emit(0, 1, "Searching...")
            if self._mode == "album":
                payload = tagger.search_album_with_diagnostics(
                    self._paths,
                    artist_hint=self._artist_hint,
                    album_hint=self._album_hint,
                )
            else:
                if not self._paths:
                    self.finished.emit({"candidates": [], "source_errors": {}, "source_counts": {}})
                    return
                payload = tagger.search_item_with_diagnostics(
                    self._paths[0],
                    artist_hint=self._artist_hint,
                    title_hint=self._title_hint,
                )
            candidates = payload.get("candidates", [])
            source_errors = payload.get("source_errors", {})
            if source_errors:
                unavailable = ", ".join(f"{name} unavailable" for name in source_errors)
                self.progress.emit(1, 1, f"Found {len(candidates)} candidates ({unavailable})")
            else:
                self.progress.emit(1, 1, f"Found {len(candidates)} candidates")
            self.finished.emit(payload)
        except Exception as exc:
            self.error.emit(str(exc))


class ArtworkPreviewWorker(BaseWorker):
    """Downloads artwork bytes from selected candidate URLs."""

    def __init__(
        self,
        *,
        match: MatchCandidate,
        request_id: int,
    ) -> None:
        super().__init__()
        self._match = match
        self._request_id = request_id

    def run(self) -> None:
        self.started.emit()
        try:
            raw = getattr(self._match, "raw_match", None)
            urls = []
            if isinstance(raw, dict):
                raw_urls = raw.get("artwork_urls", [])
                if isinstance(raw_urls, list):
                    urls = [str(url) for url in raw_urls if str(url).strip()]
            if not urls:
                self.finished.emit(
                    {
                        "request_id": self._request_id,
                        "data": b"",
                        "mime": "",
                        "message": "No artwork URL available for this candidate",
                    }
                )
                return

            self.progress.emit(0, 1, "Downloading artwork preview...")
            expanded_urls = AutoTagger._expand_artwork_urls(urls)
            artwork = AutoTagger._download_artwork_from_urls(urls)
            if self._is_cancelled:
                self.cancelled.emit()
                return

            if not artwork:
                self.finished.emit(
                    {
                        "request_id": self._request_id,
                        "data": b"",
                        "mime": "",
                        "message": (
                            f"Could not download artwork preview "
                            f"(tried {len(expanded_urls)} URL(s))"
                        ),
                    }
                )
                return

            data, mime = artwork
            self.progress.emit(1, 1, "Artwork preview ready")
            self.finished.emit(
                {
                    "request_id": self._request_id,
                    "data": data,
                    "mime": mime,
                    "message": "",
                }
            )
        except Exception as exc:
            self.error.emit(str(exc))
