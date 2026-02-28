"""Tab 3: Search MusicBrainz/Discogs, pick match, apply tags."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import cast

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QSizePolicy,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from musicorg.core.autotagger import MatchCandidate
from musicorg.ui.widgets.match_list import MatchList
from musicorg.ui.widgets.progress_bar import ProgressIndicator
from musicorg.ui.utils import safe_disconnect_multiple
from musicorg.workers.artwork_worker import ArtworkPreviewWorker
from musicorg.workers.autotag_worker import ApplyMatchWorker, AutoTagWorker, SearchMode


class AutoTagPanel(QDialog):
    """Dialog for auto-tagging files via MusicBrainz/Discogs lookup."""

    tags_applied = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Auto-Tag")
        self.resize(750, 600)
        self._files: list[Path] = []
        self._search_worker: AutoTagWorker | None = None
        self._search_thread: QThread | None = None
        self._search_in_progress = False
        self._apply_worker: ApplyMatchWorker | None = None
        self._apply_thread: QThread | None = None
        self._preview_worker: ArtworkPreviewWorker | None = None
        self._preview_thread: QThread | None = None
        self._preview_request_id: int = 0
        self._cache_db_path = ""
        self._discogs_token = ""

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Files info
        self._files_label = QLabel("No files loaded. Send files from Source tab.")
        layout.addWidget(self._files_label)

        # Search controls
        search_group = QGroupBox("Search")
        search_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        search_layout = QFormLayout(search_group)
        search_layout.setContentsMargins(6, 6, 6, 6)
        search_layout.setHorizontalSpacing(6)
        search_layout.setVerticalSpacing(6)
        self._artist_edit = QLineEdit()
        self._album_edit = QLineEdit()
        self._title_edit = QLineEdit()
        self._artist_edit.textChanged.connect(self._refresh_search_controls)
        self._album_edit.textChanged.connect(self._refresh_search_controls)
        self._title_edit.textChanged.connect(self._refresh_search_controls)
        search_layout.addRow("Artist:", self._artist_edit)
        search_layout.addRow("Album:", self._album_edit)
        search_layout.addRow("Title:", self._title_edit)

        search_btn_layout = QHBoxLayout()
        search_btn_layout.setContentsMargins(0, 2, 0, 0)
        search_btn_layout.setSpacing(6)
        self._search_btn = QPushButton("Search Album")
        self._search_btn.setEnabled(False)
        self._search_btn.clicked.connect(self._start_search)
        self._search_single_btn = QPushButton("Search Single")
        self._search_single_btn.setEnabled(False)
        self._search_single_btn.clicked.connect(self._start_search_single)
        search_btn_layout.addWidget(self._search_btn)
        search_btn_layout.addWidget(self._search_single_btn)
        search_btn_layout.addStretch()
        search_layout.addRow(search_btn_layout)
        layout.addWidget(search_group)

        # Splitter for match list and track comparison
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(2)

        # Match candidates
        match_group = QGroupBox("Match Candidates")
        match_layout = QVBoxLayout(match_group)
        match_layout.setContentsMargins(6, 6, 6, 6)
        match_layout.setSpacing(4)
        self._source_status_label = QLabel("")
        self._source_status_label.setObjectName("StatusMuted")
        self._source_status_label.setWordWrap(True)
        match_layout.addWidget(self._source_status_label)
        self._match_list = MatchList()
        self._match_list.match_selected.connect(self._on_match_selected)
        match_layout.addWidget(self._match_list)
        self._set_source_status({}, {})
        splitter.addWidget(match_group)

        # Track comparison
        track_group = QGroupBox("Track Details")
        track_group.setMinimumHeight(170)
        track_layout = QVBoxLayout(track_group)
        track_layout.setContentsMargins(6, 6, 6, 6)
        track_layout.setSpacing(4)
        self._track_table = QTableWidget()
        self._track_table.setColumnCount(4)
        self._track_table.setHorizontalHeaderLabels(
            ["#", "Title", "Artist", "Length"]
        )
        self._track_table.verticalHeader().setVisible(False)
        self._track_table.verticalHeader().setDefaultSectionSize(24)
        self._track_table.setAlternatingRowColors(True)
        self._track_table.setShowGrid(False)
        self._track_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._track_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        track_header = self._track_table.horizontalHeader()
        track_header.setStretchLastSection(True)
        track_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        track_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        track_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        track_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        artwork_row = QHBoxLayout()
        artwork_row.setContentsMargins(0, 0, 0, 4)
        artwork_row.setSpacing(8)
        self._artwork_preview = QLabel("No Preview")
        self._artwork_preview.setObjectName("AlbumCover")
        self._artwork_preview.setFixedSize(64, 64)
        self._artwork_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._artwork_hint_label = QLabel("No artwork")
        self._artwork_hint_label.setObjectName("StatusMuted")
        self._artwork_hint_label.setWordWrap(True)
        artwork_row.addWidget(self._artwork_preview)
        artwork_row.addWidget(self._artwork_hint_label, 1)
        track_layout.addLayout(artwork_row)
        track_layout.addWidget(self._track_table)
        splitter.addWidget(track_group)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([320, 200])

        layout.addWidget(splitter, 1)

        # Apply button
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)
        self._apply_btn = QPushButton("Apply Match")
        self._apply_btn.setProperty("role", "accent")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._apply_match)
        btn_layout.addStretch()
        btn_layout.addWidget(self._apply_btn)
        layout.addLayout(btn_layout)

        # Progress
        self._progress = ProgressIndicator()
        layout.addWidget(self._progress)
        self._refresh_search_controls()

    def set_cache_db_path(self, path: str) -> None:
        self._cache_db_path = path

    def set_discogs_token(self, token: str) -> None:
        self._discogs_token = token.strip()

    def load_files(self, paths: list[Path]) -> None:
        """Load files for auto-tagging."""
        self._files = list(paths)
        count = len(self._files)
        if count:
            self._files_label.setText(f"{count} file(s) loaded for auto-tagging")
        else:
            self._files_label.setText("No files loaded. Send files from Source tab.")
        self._match_list.match_model.clear()
        self._track_table.setRowCount(0)
        self._apply_btn.setEnabled(False)
        self._cancel_artwork_preview()
        self._clear_artwork_preview()
        self._set_source_status({}, {})

        # Pre-fill hints from first file's tags
        if self._files:
            try:
                from musicorg.core.tagger import TagManager
                tag_reader = TagManager()
                tags = tag_reader.read(self._files[0])
                self._artist_edit.setText(tags.albumartist or tags.artist)
                self._album_edit.setText(tags.album)
                self._title_edit.setText(tags.title)
            except Exception as exc:
                self._progress.finish(
                    f"Loaded files, but could not read tag hints: {exc}"
                )
        self._refresh_search_controls()

    def _start_search(self) -> None:
        self._do_search("album")

    def _start_search_single(self) -> None:
        self._do_search("single")

    def _do_search(self, mode: SearchMode) -> None:
        if self._search_in_progress:
            return

        artist_hint = self._artist_edit.text().strip()
        album_hint = self._album_edit.text().strip()
        title_hint = self._title_edit.text().strip()
        if mode == "single" and len(self._files) != 1:
            QMessageBox.information(
                self, "Single Search",
                "Load exactly one file to use Search Single."
            )
            return
        if mode == "album" and not self._files:
            QMessageBox.information(
                self, "Missing Files",
                "Load files from Source before running album search."
            )
            return

        self._clear_artwork_preview()
        self._search_in_progress = True
        self._refresh_search_controls()
        self._source_status_label.setText("Searching MusicBrainz and Discogs...")
        self._progress.start("Searching...")

        search_worker = AutoTagWorker(
            paths=self._files,
            artist_hint=artist_hint,
            album_hint=album_hint,
            title_hint=title_hint,
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
        search_thread.finished.connect(
            partial(self._cleanup_search, search_worker, search_thread)
        )

        self._search_worker = search_worker
        self._search_thread = search_thread
        search_thread.start()

    def _on_search_done(self, payload: object) -> None:
        try:
            candidates, source_errors, source_counts = self._coerce_search_payload(payload)
            self._match_list.match_model.set_candidates(candidates)
            self._set_source_status(source_counts, source_errors, candidates)
            count = len(candidates)
            if source_errors:
                self._progress.finish(
                    f"Found {count} candidate(s) ({self._format_source_errors(source_errors)})"
                )
            else:
                self._progress.finish(f"Found {count} candidate(s)")
        except Exception as exc:
            self._progress.finish(f"Error processing results: {exc}")
        finally:
            self._search_in_progress = False
            self._refresh_search_controls()

    def _on_search_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, message)

    def _on_search_error(self, error_message: str) -> None:
        self._search_in_progress = False
        self._refresh_search_controls()
        self._source_status_label.setText("MusicBrainz: unavailable | Discogs: unavailable")
        self._progress.finish(f"Error: {error_message}")
        QMessageBox.critical(self, "Search Error", error_message)

    def _refresh_search_controls(self) -> None:
        single_file = len(self._files) == 1
        if self._search_in_progress:
            self._search_btn.setEnabled(False)
            self._search_single_btn.setEnabled(False)
        else:
            self._search_btn.setEnabled(bool(self._files))
            self._search_single_btn.setEnabled(single_file)

        # Swap accent: single file → "Search Single" is the primary action
        album_role = "" if single_file else "accent"
        single_role = "accent" if single_file else ""
        if self._search_btn.property("role") != album_role:
            self._search_btn.setProperty("role", album_role)
            self._search_btn.style().unpolish(self._search_btn)
            self._search_btn.style().polish(self._search_btn)
            self._search_btn.update()
        if self._search_single_btn.property("role") != single_role:
            self._search_single_btn.setProperty("role", single_role)
            self._search_single_btn.style().unpolish(self._search_single_btn)
            self._search_single_btn.style().polish(self._search_single_btn)
            self._search_single_btn.update()

    @staticmethod
    def _format_source_errors(source_errors: dict[str, str]) -> str:
        parts: list[str] = []
        for source, message in source_errors.items():
            normalized = " ".join(str(message).split())
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
            counts[name] = max(0, source_counts.get(name, 0))
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

    def _on_match_selected(self, row: int) -> None:
        candidate = self._match_list.match_model.get_candidate(row)
        if not candidate:
            return

        self._apply_btn.setEnabled(True)

        # Show track details
        tracks = candidate.tracks
        self._track_table.setRowCount(len(tracks))
        for row_index, track_row in enumerate(tracks):
            self._track_table.setItem(
                row_index,
                0,
                QTableWidgetItem(str(track_row.get("track", ""))),
            )
            self._track_table.setItem(
                row_index,
                1,
                QTableWidgetItem(track_row.get("title", "")),
            )
            self._track_table.setItem(
                row_index,
                2,
                QTableWidgetItem(track_row.get("artist", "")),
            )
            length = track_row.get("length", 0)
            if length:
                mins, secs = divmod(int(length), 60)
                self._track_table.setItem(
                    row_index,
                    3,
                    QTableWidgetItem(f"{mins}:{secs:02d}"),
                )
            else:
                self._track_table.setItem(row_index, 3, QTableWidgetItem(""))

        self._start_artwork_preview(candidate)

    def _start_artwork_preview(self, candidate: MatchCandidate) -> None:
        self._cancel_artwork_preview()
        self._clear_artwork_preview()
        self._artwork_hint_label.setText("Loading artwork...")
        self._preview_request_id += 1

        worker = ArtworkPreviewWorker(match=candidate, request_id=self._preview_request_id)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_preview_done, Qt.ConnectionType.QueuedConnection)
        worker.error.connect(self._on_preview_error, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(self._cleanup_preview)
        self._preview_worker = worker
        self._preview_thread = thread
        thread.start()

    def _on_preview_done(self, payload: object) -> None:
        if not isinstance(payload, dict):
            self._artwork_hint_label.setText("No artwork")
            return
        if payload.get("request_id") != self._preview_request_id:
            return  # stale result from a previous selection
        data = payload.get("data") or b""
        message = str(payload.get("message") or "")
        if data:
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                scaled = pixmap.scaled(
                    self._artwork_preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._artwork_preview.setPixmap(scaled)
                self._artwork_preview.setText("")
                size_kb = max(1, len(data) // 1024)
                self._artwork_hint_label.setText(
                    f"Artwork: {pixmap.width()}×{pixmap.height()} px, {size_kb} KB"
                )
            else:
                self._artwork_hint_label.setText("Artwork: unreadable image data")
        else:
            self._artwork_hint_label.setText(message or "No artwork available")

    def _on_preview_error(self, _msg: str) -> None:
        self._artwork_hint_label.setText("Artwork unavailable")

    def _cancel_artwork_preview(self) -> None:
        if self._preview_worker:
            self._preview_worker.cancel()
        if self._preview_thread and self._preview_thread.isRunning():
            self._preview_thread.quit()
            self._preview_thread.wait()

    def _cleanup_preview(self) -> None:
        worker = self._preview_worker
        thread = self._preview_thread
        if worker and thread:
            safe_disconnect_multiple([
                (worker.finished, self._on_preview_done),
                (worker.error, self._on_preview_error),
                (worker.finished, thread.quit),
                (worker.error, thread.quit),
            ])
        if worker:
            worker.deleteLater()
            self._preview_worker = None
        if thread:
            thread.deleteLater()
            self._preview_thread = None

    def _clear_artwork_preview(self) -> None:
        self._artwork_preview.setPixmap(QPixmap())
        self._artwork_preview.setText("No Preview")
        self._artwork_hint_label.setText("No artwork")

    def _apply_match(self) -> None:
        candidate = self._match_list.selected_candidate()
        if not candidate or not self._files:
            return

        self._apply_btn.setEnabled(False)
        self._progress.start("Applying match...")

        self._apply_worker = ApplyMatchWorker(
            self._files,
            candidate,
            cache_db_path=self._cache_db_path,
            discogs_token=self._discogs_token,
        )
        self._apply_thread = QThread()
        self._apply_worker.moveToThread(self._apply_thread)
        self._apply_thread.started.connect(self._apply_worker.run)
        self._apply_worker.progress.connect(
            self._on_apply_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        self._apply_worker.finished.connect(self._on_apply_done)
        self._apply_worker.error.connect(self._on_apply_error)
        self._apply_worker.finished.connect(self._apply_thread.quit)
        self._apply_worker.error.connect(self._apply_thread.quit)
        self._apply_thread.finished.connect(self._cleanup_apply)
        self._apply_thread.start()

    def _on_apply_done(self, success: bool) -> None:
        try:
            if success:
                self._progress.finish("Tags applied successfully")
                self.tags_applied.emit()
            else:
                self._progress.finish("Failed to apply tags")
        finally:
            self._apply_btn.setEnabled(True)

    def _on_apply_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, message)

    def _on_apply_error(self, error_message: str) -> None:
        self._progress.finish(f"Error: {error_message}")
        self._apply_btn.setEnabled(True)
        QMessageBox.critical(self, "Apply Error", error_message)

    @staticmethod
    def _coerce_search_payload(
        payload: object,
    ) -> tuple[list[MatchCandidate], dict[str, str], dict[str, int]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, MatchCandidate)], {}, {}
        if not isinstance(payload, dict):
            return [], {}, {}
        typed_payload = cast(dict[str, object], payload)
        candidates_obj = typed_payload.get("candidates", [])
        source_errors_obj = typed_payload.get("source_errors", {})
        source_counts_obj = typed_payload.get("source_counts", {})

        candidates = (
            [item for item in candidates_obj if isinstance(item, MatchCandidate)]
            if isinstance(candidates_obj, list)
            else []
        )
        source_errors: dict[str, str] = {}
        if isinstance(source_errors_obj, dict):
            source_errors = {
                str(source): str(error_message)
                for source, error_message in source_errors_obj.items()
            }
        source_counts: dict[str, int] = {}
        if isinstance(source_counts_obj, dict):
            for source, value in source_counts_obj.items():
                try:
                    source_counts[str(source)] = max(0, int(value))
                except (TypeError, ValueError):
                    continue
        return candidates, source_errors, source_counts

    def _cleanup_search(
        self,
        search_worker: AutoTagWorker,
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

    def _cleanup_apply(self) -> None:
        apply_worker = self._apply_worker
        apply_thread = self._apply_thread
        if apply_worker and apply_thread:
            safe_disconnect_multiple([
                (apply_worker.progress, self._on_apply_progress),
                (apply_worker.finished, self._on_apply_done),
                (apply_worker.error, self._on_apply_error),
                (apply_worker.finished, apply_thread.quit),
                (apply_worker.error, apply_thread.quit),
            ])
        if apply_worker:
            apply_worker.deleteLater()
            self._apply_worker = None
        if apply_thread:
            apply_thread.deleteLater()
            self._apply_thread = None

    def shutdown(self, timeout_ms: int = 3000) -> None:
        if self._search_worker:
            self._search_worker.cancel()
        if self._apply_worker:
            self._apply_worker.cancel()
        self._cancel_artwork_preview()
        if self._search_thread and self._search_thread.isRunning():
            self._search_thread.quit()
            self._search_thread.wait()
        if self._apply_thread and self._apply_thread.isRunning():
            self._apply_thread.quit()
            self._apply_thread.wait()
        if self._search_worker and self._search_thread:
            self._cleanup_search(self._search_worker, self._search_thread)
        self._cleanup_apply()
