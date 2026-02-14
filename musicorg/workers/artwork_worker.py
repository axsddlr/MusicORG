"""Workers for artwork search and preview download."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypedDict

from musicorg.core.autotagger import AutoTagger, SearchDiagnostics
from musicorg.core.tag_cache import TagCache
from musicorg.core.tagger import TagManager
from musicorg.workers.base_worker import BaseWorker

if TYPE_CHECKING:
    from musicorg.core.autotagger import MatchCandidate


SearchMode = Literal["album", "single"]


class PreviewResult(TypedDict):
    request_id: int
    data: bytes
    mime: str
    message: str


ApplyFailure = tuple[Path, str]


class ArtworkApplyResult(TypedDict):
    total: int
    updated: int
    skipped: int
    failed: list[ApplyFailure]


class ArtworkSearchWorker(BaseWorker):
    """Searches metadata providers for artwork-capable match candidates."""

    def __init__(
        self,
        *,
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
            tagger = AutoTagger(discogs_token=self._discogs_token)
            self.progress.emit(0, 1, "Searching...")
            search_result: SearchDiagnostics
            if self._mode == "album":
                search_result = tagger.search_album_with_diagnostics(
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
                search_result = tagger.search_item_with_diagnostics(
                    self._paths[0],
                    artist_hint=self._artist_hint,
                    title_hint=self._title_hint,
                )
            candidates = search_result.get("candidates", [])
            source_errors = search_result.get("source_errors", {})
            if source_errors:
                unavailable = ", ".join(f"{name} unavailable" for name in source_errors)
                self.progress.emit(1, 1, f"Found {len(candidates)} candidates ({unavailable})")
            else:
                self.progress.emit(1, 1, f"Found {len(candidates)} candidates")
            self.finished.emit(search_result)
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
            match_payload = getattr(self._match, "raw_match", None)
            artwork_urls: list[str] = []
            if isinstance(match_payload, dict):
                raw_artwork_urls = match_payload.get("artwork_urls", [])
                if isinstance(raw_artwork_urls, list):
                    artwork_urls = [
                        str(url).strip()
                        for url in raw_artwork_urls
                        if str(url).strip()
                    ]
            if not artwork_urls:
                self.finished.emit(self._build_preview_result(
                    message="No artwork URL available for this candidate",
                ))
                return

            self.progress.emit(0, 1, "Downloading artwork preview...")
            expanded_urls = AutoTagger._expand_artwork_urls(artwork_urls)
            artwork = AutoTagger._download_artwork_from_urls(artwork_urls)
            if self._is_cancelled:
                self.cancelled.emit()
                return

            if not artwork:
                self.finished.emit(self._build_preview_result(
                    message=(
                        f"Could not download artwork preview "
                        f"(tried {len(expanded_urls)} URL(s))"
                    ),
                ))
                return

            image_data, image_mime = artwork
            self.progress.emit(1, 1, "Artwork preview ready")
            self.finished.emit(
                self._build_preview_result(
                    data=image_data,
                    mime=image_mime,
                )
            )
        except Exception as exc:
            self.error.emit(str(exc))

    def _build_preview_result(
        self,
        *,
        data: bytes = b"",
        mime: str = "",
        message: str = "",
    ) -> PreviewResult:
        return {
            "request_id": self._request_id,
            "data": data,
            "mime": mime,
            "message": message,
        }


class ArtworkApplyWorker(BaseWorker):
    """Embeds selected artwork into a set of files."""

    def __init__(
        self,
        *,
        paths: list[str | Path],
        artwork_data: bytes,
        artwork_mime: str,
        only_missing: bool = False,
        cache_db_path: str = "",
    ) -> None:
        super().__init__()
        self._paths = [Path(path) for path in paths]
        self._artwork_data = bytes(artwork_data)
        self._artwork_mime = artwork_mime
        self._only_missing = only_missing
        self._cache_db_path = cache_db_path

    def run(self) -> None:
        self.started.emit()
        try:
            total_files = len(self._paths)
            if total_files == 0:
                self.finished.emit(self._build_result(total=0, updated=0, skipped=0, failed=[]))
                return

            tag_writer = TagManager()
            updated_count = 0
            skipped_count = 0
            failed_writes: list[ApplyFailure] = []
            updated_paths: list[Path] = []

            for index, path in enumerate(self._paths):
                if self._is_cancelled:
                    self.cancelled.emit()
                    return
                try:
                    current_tags = tag_writer.read(path)
                except Exception as exc:
                    failed_writes.append((path, str(exc) or exc.__class__.__name__))
                    self.progress.emit(index + 1, total_files, path.name)
                    continue

                if self._only_missing and current_tags.artwork_data:
                    skipped_count += 1
                    self.progress.emit(index + 1, total_files, path.name)
                    continue

                updated_tags = replace(
                    current_tags,
                    artwork_data=self._artwork_data,
                    artwork_mime=self._artwork_mime or "image/jpeg",
                )
                try:
                    tag_writer.write(path, updated_tags)
                    updated_count += 1
                    updated_paths.append(path)
                except Exception as exc:
                    failed_writes.append((path, str(exc) or exc.__class__.__name__))

                self.progress.emit(index + 1, total_files, path.name)

            self._invalidate_cache(updated_paths)
            self.finished.emit(
                self._build_result(
                    total=total_files,
                    updated=updated_count,
                    skipped=skipped_count,
                    failed=failed_writes,
                )
            )
        except Exception as exc:
            self.error.emit(str(exc))

    def _invalidate_cache(self, paths: list[Path]) -> None:
        if not self._cache_db_path or not paths:
            return
        cache: TagCache | None = None
        try:
            cache = TagCache(self._cache_db_path)
            cache.open()
            cache.invalidate_many(paths)
        except Exception:
            pass
        finally:
            if cache is not None:
                try:
                    cache.close()
                except Exception:
                    pass

    @staticmethod
    def _build_result(
        *,
        total: int,
        updated: int,
        skipped: int,
        failed: list[ApplyFailure],
    ) -> ArtworkApplyResult:
        return {
            "total": total,
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
        }
