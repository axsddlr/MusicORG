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
from musicorg.workers.artwork_worker import ArtworkPreviewWorker, ArtworkSearchWorker


class ArtworkDownloaderPanel(QDialog):
    """Dialog for searching artwork candidates and previewing covers."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Artwork Downloader")
        self.resize(760, 560)

        self._files: list[Path] = []
        self._candidates: list[MatchCandidate] = []
        self._selected_artwork_data: bytes = b""
        self._selected_artwork_mime: str = ""
        self._preview_source_pixmap = QPixmap()
        self._preview_request_id = 0
        self._cache_db_path = ""
        self._discogs_token = ""
        self._search_worker: ArtworkSearchWorker | None = None
        self._search_thread: QThread | None = None
        self._search_in_progress = False
        self._preview_worker: ArtworkPreviewWorker | None = None
        self._preview_thread: QThread | None = None

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
        self._apply_btn.setToolTip("Apply flow is planned for Phase 3.")
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
        self._cancel_preview()
        self._files = list(paths)
        count = len(self._files)
        self._candidates = []
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
        if self._search_in_progress:
            self._search_album_btn.setEnabled(False)
            self._search_single_btn.setEnabled(False)
            self._only_missing_chk.setEnabled(False)
            self._apply_btn.setEnabled(False)
            return
        has_files = bool(self._files)
        self._search_album_btn.setEnabled(has_files)
        self._search_single_btn.setEnabled(len(self._files) == 1)
        self._only_missing_chk.setEnabled(has_files)
        # Apply remains disabled until Phase 3.
        self._apply_btn.setEnabled(False)

    def _start_search_album(self) -> None:
        self._start_search("album")

    def _start_search_single(self) -> None:
        self._start_search("single")

    def _start_search(self, mode: str) -> None:
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
        self._refresh_controls()
        self._match_list.match_model.clear()
        self._candidates = []
        self._set_source_status({}, {})
        self._clear_preview("Searching providers...")
        self._progress.start("Searching...")

        worker = ArtworkSearchWorker(
            paths=self._files,
            artist_hint=self._artist_edit.text().strip(),
            album_hint=self._album_edit.text().strip(),
            title_hint=self._title_edit.text().strip(),
            mode=mode,
            discogs_token=self._discogs_token,
        )
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(
            self._on_search_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(self._on_search_done)
        worker.error.connect(self._on_search_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(partial(self._cleanup_search, worker, thread))

        self._search_worker = worker
        self._search_thread = thread
        thread.start()

    def _on_search_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, message)

    def _on_search_done(self, payload: object) -> None:
        candidates: list[MatchCandidate] = []
        source_errors: dict[str, str] = {}
        source_counts: dict[str, object] = {}
        if isinstance(payload, dict):
            candidates_obj = payload.get("candidates", [])
            source_errors_obj = payload.get("source_errors", {})
            source_counts_obj = payload.get("source_counts", {})
            if isinstance(candidates_obj, list):
                candidates = candidates_obj
            if isinstance(source_errors_obj, dict):
                source_errors = source_errors_obj
            if isinstance(source_counts_obj, dict):
                source_counts = source_counts_obj

        self._candidates = candidates
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

    def _on_search_error(self, msg: str) -> None:
        self._search_in_progress = False
        self._refresh_controls()
        self._set_source_status({}, {"MusicBrainz": msg, "Discogs": msg})
        self._clear_preview("Search failed")
        self._progress.finish(f"Error: {msg}")
        QMessageBox.critical(self, "Search Error", msg)

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
        request_id = self._preview_request_id
        self._clear_preview("Downloading artwork preview...")
        self._preview_title_label.setText(
            f"{candidate.artist} - {candidate.album} ({candidate.source})"
        )
        self._progress.start("Downloading artwork preview...")

        worker = ArtworkPreviewWorker(
            match=candidate,
            request_id=request_id,
        )
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(
            self._on_preview_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(self._on_preview_done)
        worker.error.connect(self._on_preview_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(partial(self._cleanup_preview, worker, thread))

        self._preview_worker = worker
        self._preview_thread = thread
        thread.start()

    def _on_preview_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, message)

    def _on_preview_done(self, payload: object) -> None:
        if not isinstance(payload, dict):
            self._clear_preview("No preview data available")
            self._progress.finish("No artwork preview available")
            return

        try:
            request_id = int(payload.get("request_id", -1))
        except (TypeError, ValueError):
            request_id = -1
        if request_id != self._preview_request_id:
            return

        data_obj = payload.get("data", b"")
        data = data_obj if isinstance(data_obj, (bytes, bytearray)) else b""
        mime = str(payload.get("mime", "") or "")
        message = str(payload.get("message", "") or "")

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

        size_kb = max(1, len(self._selected_artwork_data) // 1024)
        mime_label = mime if mime else "image/*"
        self._preview_meta_label.setText(f"{mime_label} - {size_kb} KB")
        self._progress.finish("Artwork preview ready")

    def _on_preview_error(self, msg: str) -> None:
        self._clear_preview("Preview download failed")
        self._progress.finish(f"Preview error: {msg}")

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
        source_counts: dict[str, object],
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

    def _apply_artwork(self) -> None:
        QMessageBox.information(
            self,
            "Artwork Downloader",
            "Artwork apply flow will be added in Phase 3.",
        )

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

    def _cleanup_search(self, worker: ArtworkSearchWorker, thread: QThread) -> None:
        try:
            worker.progress.disconnect(self._on_search_progress)
        except (RuntimeError, TypeError):
            pass
        try:
            worker.finished.disconnect(self._on_search_done)
        except (RuntimeError, TypeError):
            pass
        try:
            worker.error.disconnect(self._on_search_error)
        except (RuntimeError, TypeError):
            pass
        try:
            worker.finished.disconnect(thread.quit)
        except (RuntimeError, TypeError):
            pass
        try:
            worker.error.disconnect(thread.quit)
        except (RuntimeError, TypeError):
            pass
        worker.deleteLater()
        thread.deleteLater()
        if self._search_worker is worker:
            self._search_worker = None
        if self._search_thread is thread:
            self._search_thread = None

    def _cleanup_preview(self, worker: ArtworkPreviewWorker, thread: QThread) -> None:
        try:
            worker.progress.disconnect(self._on_preview_progress)
        except (RuntimeError, TypeError):
            pass
        try:
            worker.finished.disconnect(self._on_preview_done)
        except (RuntimeError, TypeError):
            pass
        try:
            worker.error.disconnect(self._on_preview_error)
        except (RuntimeError, TypeError):
            pass
        try:
            worker.finished.disconnect(thread.quit)
        except (RuntimeError, TypeError):
            pass
        try:
            worker.error.disconnect(thread.quit)
        except (RuntimeError, TypeError):
            pass
        worker.deleteLater()
        thread.deleteLater()
        if self._preview_worker is worker:
            self._preview_worker = None
        if self._preview_thread is thread:
            self._preview_thread = None

    def shutdown(self, timeout_ms: int = 3000) -> None:
        _ = timeout_ms
        if self._search_worker:
            self._search_worker.cancel()
        if self._preview_worker:
            self._preview_worker.cancel()
        if self._search_thread and self._search_thread.isRunning():
            self._search_thread.quit()
            self._search_thread.wait()
        if self._preview_thread and self._preview_thread.isRunning():
            self._preview_thread.quit()
            self._preview_thread.wait()
        if self._search_worker and self._search_thread:
            self._cleanup_search(self._search_worker, self._search_thread)
        if self._preview_worker and self._preview_thread:
            self._cleanup_preview(self._preview_worker, self._preview_thread)
