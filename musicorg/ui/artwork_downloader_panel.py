"""Artwork downloader dialog."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from musicorg.core.autotagger import MatchCandidate
from musicorg.core.tagger import TagManager
from musicorg.ui.widgets.match_list import MatchList
from musicorg.ui.widgets.progress_bar import ProgressIndicator
from musicorg.ui.utils import safe_disconnect_multiple
from musicorg.workers.artwork_worker import (
    ArtworkApplyResult,
    ArtworkApplyWorker,
    ArtworkPreviewWorker,
    ArtworkSearchWorker,
    PreviewResult,
    SearchMode,
)


class ArtworkDownloaderPanel(QDialog):
    """Dialog for searching artwork candidates and previewing covers."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Artwork Downloader")
        self.resize(760, 560)

        self._files: list[Path] = []
        self._selected_artwork_data: bytes = b""
        self._selected_artwork_mime: str = ""
        self._preview_source_pixmap = QPixmap()
        self._preview_request_id = 0
        self._cache_db_path = ""
        self._discogs_token = ""
        self._search_worker: ArtworkSearchWorker | None = None
        self._search_thread: QThread | None = None
        self._search_in_progress = False
        self._apply_worker: ArtworkApplyWorker | None = None
        self._apply_thread: QThread | None = None
        self._apply_in_progress = False
        self._preview_worker: ArtworkPreviewWorker | None = None
        self._preview_thread: QThread | None = None
        self._preview_in_progress = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self._files_label = QLabel("No files loaded. Send files from Source.")
        layout.addWidget(self._files_label)

        search_group = QGroupBox("Search")
        search_layout = QFormLayout(search_group)
        search_layout.setContentsMargins(6, 6, 6, 6)
        search_layout.setHorizontalSpacing(6)
        search_layout.setVerticalSpacing(6)
        self._artist_edit = QLineEdit()
        self._album_edit = QLineEdit()
        self._title_edit = QLineEdit()
        search_layout.addRow("Artist:", self._artist_edit)
        search_layout.addRow("Album:", self._album_edit)
        search_layout.addRow("Title:", self._title_edit)

        search_btn_layout = QHBoxLayout()
        search_btn_layout.setContentsMargins(0, 2, 0, 0)
        search_btn_layout.setSpacing(6)
        self._search_album_btn = QPushButton("Search Album")
        self._search_album_btn.setProperty("role", "accent")
        self._search_album_btn.clicked.connect(self._start_search_album)
        self._search_single_btn = QPushButton("Search Single")
        self._search_single_btn.clicked.connect(self._start_search_single)
        search_btn_layout.addWidget(self._search_album_btn)
        search_btn_layout.addWidget(self._search_single_btn)
        search_btn_layout.addStretch()
        search_layout.addRow(search_btn_layout)
        layout.addWidget(search_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(2)

        candidate_group = QGroupBox("Match Candidates")
        candidate_layout = QVBoxLayout(candidate_group)
        candidate_layout.setContentsMargins(6, 6, 6, 6)
        candidate_layout.setSpacing(4)
        self._source_status_label = QLabel("")
        self._source_status_label.setObjectName("StatusMuted")
        self._source_status_label.setWordWrap(True)
        candidate_layout.addWidget(self._source_status_label)
        self._match_list = MatchList()
        self._match_list.match_selected.connect(self._on_match_selected)
        candidate_layout.addWidget(self._match_list)
        splitter.addWidget(candidate_group)

        preview_group = QGroupBox("Artwork Preview")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_layout.setSpacing(6)
        self._preview_title_label = QLabel("No candidate selected")
        self._preview_title_label.setObjectName("SectionHeader")
        self._preview_title_label.setWordWrap(True)
        preview_layout.addWidget(self._preview_title_label)
        self._preview_image_label = QLabel("No preview")
        self._preview_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_image_label.setMinimumHeight(260)
        self._preview_image_label.setObjectName("AlbumCover")
        preview_layout.addWidget(self._preview_image_label, 1)
        self._preview_meta_label = QLabel("")
        self._preview_meta_label.setObjectName("StatusMuted")
        self._preview_meta_label.setWordWrap(True)
        preview_layout.addWidget(self._preview_meta_label)
        splitter.addWidget(preview_group)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([460, 300])
        layout.addWidget(splitter, 1)

        apply_layout = QHBoxLayout()
        apply_layout.setContentsMargins(0, 0, 0, 0)
        apply_layout.setSpacing(8)
        self._only_missing_chk = QCheckBox("Only fill missing artwork")
        self._apply_btn = QPushButton("Apply Artwork")
        self._apply_btn.setProperty("role", "accent")
        self._apply_btn.setToolTip("Write the current preview artwork to loaded files.")
        self._apply_btn.clicked.connect(self._apply_artwork)
        apply_layout.addWidget(self._only_missing_chk)
        apply_layout.addStretch()
        apply_layout.addWidget(self._apply_btn)
        layout.addLayout(apply_layout)

        self._progress = ProgressIndicator()
        layout.addWidget(self._progress)
        self._refresh_controls()

    def set_cache_db_path(self, path: str) -> None:
        self._cache_db_path = path

    def set_discogs_token(self, token: str) -> None:
        self._discogs_token = token.strip()

    def load_files(self, paths: list[Path]) -> None:
        if self._apply_in_progress:
            QMessageBox.information(
                self,
                "Artwork Apply In Progress",
                "Wait for the current artwork apply job to finish.",
            )
            return
        self._cancel_preview()
        self._files = list(paths)
        count = len(self._files)
        self._match_list.match_model.clear()
        self._set_source_status({}, {})
        self._clear_preview()
        if count == 0:
            self._files_label.setText("No files loaded. Send files from Source.")
            self._artist_edit.clear()
            self._album_edit.clear()
            self._title_edit.clear()
            self._refresh_controls()
            return

        self._files_label.setText(f"{count} file(s) loaded for artwork download")
        self._prefill_hints()
        self._refresh_controls()

    def _prefill_hints(self) -> None:
        if not self._files:
            return
        try:
            tags = TagManager().read(self._files[0])
        except Exception:
            return
        self._artist_edit.setText(tags.albumartist or tags.artist)
        self._album_edit.setText(tags.album)
        self._title_edit.setText(tags.title)

    def _refresh_controls(self) -> None:
        if self._search_in_progress or self._apply_in_progress:
            self._search_album_btn.setEnabled(False)
            self._search_single_btn.setEnabled(False)
            self._only_missing_chk.setEnabled(False)
            self._apply_btn.setEnabled(False)
            return
        has_files = bool(self._files)
        self._search_album_btn.setEnabled(has_files)
        self._search_single_btn.setEnabled(len(self._files) == 1)
        self._only_missing_chk.setEnabled(has_files)
        has_preview = bool(self._selected_artwork_data)
        self._apply_btn.setEnabled(has_files and has_preview and not self._preview_in_progress)

    def _start_search_album(self) -> None:
        self._start_search("album")

    def _start_search_single(self) -> None:
        self._start_search("single")

    def _start_search(self, mode: SearchMode) -> None:
        if self._search_in_progress:
            return
        if mode == "single" and len(self._files) != 1:
            QMessageBox.information(
                self,
                "Single Search",
                "Load exactly one file to use Search Single.",
            )
            return
        if mode == "album" and not self._files:
            QMessageBox.information(
                self,
                "Missing Files",
                "Load files from Source before running album search.",
            )
            return

        self._search_in_progress = True
        self._cancel_preview()
        self._refresh_controls()
        self._match_list.match_model.clear()
        self._set_source_status({}, {})
        self._clear_preview("Searching providers...")
        self._progress.start("Searching...")

        search_worker = ArtworkSearchWorker(
            paths=self._files,
            artist_hint=self._artist_edit.text().strip(),
            album_hint=self._album_edit.text().strip(),
            title_hint=self._title_edit.text().strip(),
            mode=mode,
            discogs_token=self._discogs_token,
        )
        search_thread = QThread()
        search_worker.moveToThread(search_thread)
        search_thread.started.connect(search_worker.run)
        search_worker.progress.connect(
            self._on_search_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        search_worker.finished.connect(self._on_search_done)
        search_worker.error.connect(self._on_search_error)
        search_worker.finished.connect(search_thread.quit)
        search_worker.error.connect(search_thread.quit)
        search_thread.finished.connect(partial(self._cleanup_search, search_worker, search_thread))

        self._search_worker = search_worker
        self._search_thread = search_thread
        search_thread.start()

    def _on_search_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, message)

    def _on_search_done(self, payload: object) -> None:
        candidates, source_errors, source_counts = self._coerce_search_payload(payload)
        self._match_list.match_model.set_candidates(candidates)
        self._search_in_progress = False
        self._refresh_controls()
        self._set_source_status(source_counts, source_errors, candidates)

        if not candidates:
            self._clear_preview("No candidates found")
        else:
            self._clear_preview("Select a candidate to download preview")

        if source_errors:
            self._progress.finish(
                f"Found {len(candidates)} candidate(s) ({self._format_source_errors(source_errors)})"
            )
        else:
            self._progress.finish(f"Found {len(candidates)} candidate(s)")

    def _on_search_error(self, error_message: str) -> None:
        self._search_in_progress = False
        self._refresh_controls()
        self._set_source_status({}, {"MusicBrainz": error_message, "Discogs": error_message})
        self._clear_preview("Search failed")
        self._progress.finish(f"Error: {error_message}")
        QMessageBox.critical(self, "Search Error", error_message)

    def _on_match_selected(self, row: int) -> None:
        candidate = self._match_list.match_model.get_candidate(row)
        if not candidate:
            return
        self._preview_title_label.setText(
            f"{candidate.artist} - {candidate.album} ({candidate.source})"
        )
        self._start_preview(candidate)

    def _start_preview(self, candidate: MatchCandidate) -> None:
        self._cancel_preview()
        self._preview_request_id += 1
        self._preview_in_progress = True
        self._refresh_controls()
        request_id = self._preview_request_id
        self._clear_preview("Downloading artwork preview...")
        self._preview_title_label.setText(
            f"{candidate.artist} - {candidate.album} ({candidate.source})"
        )
        self._progress.start("Downloading artwork preview...")

        preview_worker = ArtworkPreviewWorker(
            match=candidate,
            request_id=request_id,
        )
        preview_thread = QThread()
        preview_worker.moveToThread(preview_thread)
        preview_thread.started.connect(preview_worker.run)
        preview_worker.progress.connect(
            self._on_preview_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        preview_worker.finished.connect(self._on_preview_done)
        preview_worker.error.connect(self._on_preview_error)
        preview_worker.finished.connect(preview_thread.quit)
        preview_worker.error.connect(preview_thread.quit)
        preview_thread.finished.connect(
            partial(self._cleanup_preview, preview_worker, preview_thread)
        )

        self._preview_worker = preview_worker
        self._preview_thread = preview_thread
        preview_thread.start()

    def _on_preview_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, message)

    def _on_preview_done(self, payload: object) -> None:
        preview_result = self._coerce_preview_result(payload)
        self._preview_in_progress = False
        if preview_result is None:
            self._clear_preview("No preview data available")
            self._progress.finish("No artwork preview available")
            return

        request_id = preview_result["request_id"]
        if request_id != self._preview_request_id:
            return

        data = preview_result["data"]
        mime = preview_result["mime"]
        message = preview_result["message"]

        if not data:
            self._clear_preview(message or "No artwork preview available")
            self._progress.finish(message or "No artwork preview available")
            return

        pixmap = QPixmap()
        if not pixmap.loadFromData(bytes(data)):
            self._clear_preview("Downloaded artwork could not be rendered")
            self._progress.finish("Preview image decode failed")
            return

        self._selected_artwork_data = bytes(data)
        self._selected_artwork_mime = mime
        self._preview_source_pixmap = pixmap
        self._render_preview_pixmap()
        self._refresh_controls()

        size_kb = max(1, len(self._selected_artwork_data) // 1024)
        mime_label = mime if mime else "image/*"
        self._preview_meta_label.setText(f"{mime_label} - {size_kb} KB")
        self._progress.finish("Artwork preview ready")

    def _on_preview_error(self, error_message: str) -> None:
        self._preview_in_progress = False
        self._refresh_controls()
        self._clear_preview("Preview download failed")
        self._progress.finish(f"Preview error: {error_message}")

    @staticmethod
    def _coerce_apply_result(payload: object) -> ArtworkApplyResult:
        if not isinstance(payload, dict):
            return {"total": 0, "updated": 0, "skipped": 0, "failed": []}
        total = 0
        updated = 0
        skipped = 0
        try:
            total = max(0, int(payload.get("total", 0)))
        except (TypeError, ValueError):
            total = 0
        try:
            updated = max(0, int(payload.get("updated", 0)))
        except (TypeError, ValueError):
            updated = 0
        try:
            skipped = max(0, int(payload.get("skipped", 0)))
        except (TypeError, ValueError):
            skipped = 0
        failed: list[tuple[Path, str]] = []
        raw_failed = payload.get("failed", [])
        if isinstance(raw_failed, list):
            for item in raw_failed:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    continue
                failed.append((Path(item[0]), str(item[1])))
        return {
            "total": total,
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
        }

    @staticmethod
    def _coerce_search_payload(
        payload: object,
    ) -> tuple[list[MatchCandidate], dict[str, str], dict[str, int]]:
        if not isinstance(payload, dict):
            return [], {}, {}

        candidates_obj = payload.get("candidates", [])
        source_errors_obj = payload.get("source_errors", {})
        source_counts_obj = payload.get("source_counts", {})

        candidates = [c for c in candidates_obj if isinstance(c, MatchCandidate)]
        source_errors: dict[str, str] = {}
        if isinstance(source_errors_obj, dict):
            source_errors = {
                str(source): str(message)
                for source, message in source_errors_obj.items()
            }
        source_counts: dict[str, int] = {}
        if isinstance(source_counts_obj, dict):
            for source, count in source_counts_obj.items():
                try:
                    source_counts[str(source)] = max(0, int(count))
                except (TypeError, ValueError):
                    continue
        return candidates, source_errors, source_counts

    @staticmethod
    def _coerce_preview_result(payload: object) -> PreviewResult | None:
        if not isinstance(payload, dict):
            return None
        try:
            request_id = int(payload.get("request_id", -1))
        except (TypeError, ValueError):
            request_id = -1
        data_obj = payload.get("data", b"")
        data = bytes(data_obj) if isinstance(data_obj, (bytes, bytearray)) else b""
        mime = str(payload.get("mime", "") or "")
        message = str(payload.get("message", "") or "")
        return {
            "request_id": request_id,
            "data": data,
            "mime": mime,
            "message": message,
        }

    @staticmethod
    def _format_source_errors(source_errors: dict[str, str]) -> str:
        parts: list[str] = []
        for source, message in source_errors.items():
            normalized = " ".join(str(message).split())
            lowered = normalized.lower()
            if "forcibly closed" in lowered or "winerror 10054" in lowered:
                normalized = "connection reset by remote host"
            elif "timed out" in lowered or "timeout" in lowered:
                normalized = "request timed out"
            elif "http error 429" in lowered:
                normalized = "rate limited (HTTP 429)"
            elif "http error 503" in lowered:
                normalized = "service unavailable (HTTP 503)"
            if len(normalized) > 90:
                normalized = normalized[:87] + "..."
            parts.append(f"{source} unavailable: {normalized}")
        return "; ".join(parts)

    def _set_source_status(
        self,
        source_counts: dict[str, int],
        source_errors: dict[str, str],
        candidates: list[MatchCandidate] | None = None,
    ) -> None:
        source_names = ("MusicBrainz", "Discogs")
        counts: dict[str, int] = {name: 0 for name in source_names}
        for name in source_names:
            raw = source_counts.get(name, 0)
            try:
                counts[name] = max(0, int(raw))
            except (TypeError, ValueError):
                counts[name] = 0
        if not source_counts and candidates:
            for candidate in candidates:
                if candidate.source in counts:
                    counts[candidate.source] += 1
        parts: list[str] = []
        for name in source_names:
            part = f"{name}: {counts[name]}"
            if name in source_errors:
                part += " (failed)"
            parts.append(part)
        self._source_status_label.setText(" | ".join(parts))

    def _clear_preview(self, message: str = "No candidate selected") -> None:
        self._selected_artwork_data = b""
        self._selected_artwork_mime = ""
        self._preview_source_pixmap = QPixmap()
        self._preview_image_label.setPixmap(QPixmap())
        self._preview_image_label.setText("No preview")
        self._preview_meta_label.setText(message)
        self._refresh_controls()

    def _apply_artwork(self) -> None:
        if self._apply_in_progress:
            return
        if not self._files:
            QMessageBox.information(self, "Artwork Downloader", "Load files before applying artwork.")
            return
        if not self._selected_artwork_data:
            QMessageBox.information(
                self,
                "Artwork Downloader",
                "Download a preview image before applying artwork.",
            )
            return

        self._apply_in_progress = True
        self._refresh_controls()
        self._progress.start("Applying artwork...")

        apply_worker = ArtworkApplyWorker(
            paths=self._files,
            artwork_data=self._selected_artwork_data,
            artwork_mime=self._selected_artwork_mime,
            only_missing=self._only_missing_chk.isChecked(),
            cache_db_path=self._cache_db_path,
        )
        apply_thread = QThread()
        apply_worker.moveToThread(apply_thread)
        apply_thread.started.connect(apply_worker.run)
        apply_worker.progress.connect(
            self._on_apply_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        apply_worker.finished.connect(self._on_apply_done)
        apply_worker.error.connect(self._on_apply_error)
        apply_worker.finished.connect(apply_thread.quit)
        apply_worker.error.connect(apply_thread.quit)
        apply_thread.finished.connect(
            partial(self._cleanup_apply, apply_worker, apply_thread)
        )
        self._apply_worker = apply_worker
        self._apply_thread = apply_thread
        apply_thread.start()

    def _on_apply_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, f"Applying: {message}")

    def _on_apply_done(self, payload: object) -> None:
        self._apply_in_progress = False
        self._refresh_controls()
        result = self._coerce_apply_result(payload)
        updated = result["updated"]
        skipped = result["skipped"]
        failed = result["failed"]
        summary = f"Artwork updated on {updated} file(s)"
        if skipped:
            summary += f", skipped {skipped}"
        if failed:
            summary += f", failed {len(failed)}"
        self._progress.finish(summary)
        if failed:
            preview = "\n".join(f"- {path.name}: {error}" for path, error in failed[:8])
            if len(failed) > 8:
                preview += f"\n... and {len(failed) - 8} more"
            QMessageBox.warning(
                self,
                "Artwork Apply Warnings",
                f"Some files failed while applying artwork:\n{preview}",
            )

    def _on_apply_error(self, error_message: str) -> None:
        self._apply_in_progress = False
        self._refresh_controls()
        self._progress.finish(f"Artwork apply error: {error_message}")
        QMessageBox.critical(self, "Artwork Apply Error", error_message)

    def _render_preview_pixmap(self) -> None:
        if self._preview_source_pixmap.isNull():
            return
        target = self._preview_image_label.size()
        if target.width() <= 1 or target.height() <= 1:
            return
        scaled = self._preview_source_pixmap.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_image_label.setText("")
        self._preview_image_label.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._preview_source_pixmap.isNull():
            self._render_preview_pixmap()

    def _cancel_preview(self) -> None:
        if self._preview_worker:
            self._preview_worker.cancel()
        if self._preview_thread and self._preview_thread.isRunning():
            self._preview_thread.quit()
            self._preview_thread.wait()
        self._preview_in_progress = False
        self._refresh_controls()

    def _cleanup_search(
        self,
        search_worker: ArtworkSearchWorker,
        search_thread: QThread,
    ) -> None:
        safe_disconnect_multiple([
            (search_worker.progress, self._on_search_progress),
            (search_worker.finished, self._on_search_done),
            (search_worker.error, self._on_search_error),
            (search_worker.finished, search_thread.quit),
            (search_worker.error, search_thread.quit),
        ])
        search_worker.deleteLater()
        search_thread.deleteLater()
        if self._search_worker is search_worker:
            self._search_worker = None
        if self._search_thread is search_thread:
            self._search_thread = None

    def _cleanup_preview(
        self,
        preview_worker: ArtworkPreviewWorker,
        preview_thread: QThread,
    ) -> None:
        safe_disconnect_multiple([
            (preview_worker.progress, self._on_preview_progress),
            (preview_worker.finished, self._on_preview_done),
            (preview_worker.error, self._on_preview_error),
            (preview_worker.finished, preview_thread.quit),
            (preview_worker.error, preview_thread.quit),
        ])
        preview_worker.deleteLater()
        preview_thread.deleteLater()
        if self._preview_worker is preview_worker:
            self._preview_worker = None
        if self._preview_thread is preview_thread:
            self._preview_thread = None

    def _cleanup_apply(
        self,
        apply_worker: ArtworkApplyWorker,
        apply_thread: QThread,
    ) -> None:
        safe_disconnect_multiple([
            (apply_worker.progress, self._on_apply_progress),
            (apply_worker.finished, self._on_apply_done),
            (apply_worker.error, self._on_apply_error),
            (apply_worker.finished, apply_thread.quit),
            (apply_worker.error, apply_thread.quit),
        ])
        apply_worker.deleteLater()
        apply_thread.deleteLater()
        if self._apply_worker is apply_worker:
            self._apply_worker = None
        if self._apply_thread is apply_thread:
            self._apply_thread = None

    def shutdown(self, timeout_ms: int = 3000) -> None:
        _ = timeout_ms
        if self._search_worker:
            self._search_worker.cancel()
        if self._apply_worker:
            self._apply_worker.cancel()
        if self._preview_worker:
            self._preview_worker.cancel()
        if self._search_thread and self._search_thread.isRunning():
            self._search_thread.quit()
            self._search_thread.wait()
        if self._apply_thread and self._apply_thread.isRunning():
            self._apply_thread.quit()
            self._apply_thread.wait()
        if self._preview_thread and self._preview_thread.isRunning():
            self._preview_thread.quit()
            self._preview_thread.wait()
        if self._search_worker and self._search_thread:
            self._cleanup_search(self._search_worker, self._search_thread)
        if self._apply_worker and self._apply_thread:
            self._cleanup_apply(self._apply_worker, self._apply_thread)
        if self._preview_worker and self._preview_thread:
            self._cleanup_preview(self._preview_worker, self._preview_thread)
