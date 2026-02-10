"""Tab 3: Search MusicBrainz/Discogs, pick match, apply tags."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from musicorg.core.autotagger import MatchCandidate
from musicorg.ui.widgets.match_list import MatchList
from musicorg.ui.widgets.progress_bar import ProgressIndicator
from musicorg.workers.autotag_worker import ApplyMatchWorker, AutoTagWorker


class AutoTagPanel(QWidget):
    """Panel for auto-tagging files via MusicBrainz/Discogs lookup."""

    tags_applied = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._files: list[Path] = []
        self._candidates: list[MatchCandidate] = []
        self._search_worker: AutoTagWorker | None = None
        self._search_thread: QThread | None = None
        self._apply_worker: ApplyMatchWorker | None = None
        self._apply_thread: QThread | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Files info
        self._files_label = QLabel("No files loaded. Send files from Source tab.")
        layout.addWidget(self._files_label)

        # Search controls
        search_group = QGroupBox("Search")
        search_layout = QFormLayout(search_group)
        self._artist_edit = QLineEdit()
        self._album_edit = QLineEdit()
        search_layout.addRow("Artist:", self._artist_edit)
        search_layout.addRow("Album:", self._album_edit)

        search_btn_layout = QHBoxLayout()
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

        # Match candidates
        match_group = QGroupBox("Match Candidates")
        match_layout = QVBoxLayout(match_group)
        self._match_list = MatchList()
        self._match_list.match_selected.connect(self._on_match_selected)
        match_layout.addWidget(self._match_list)
        splitter.addWidget(match_group)

        # Track comparison
        track_group = QGroupBox("Track Details")
        track_layout = QVBoxLayout(track_group)
        self._track_table = QTableWidget()
        self._track_table.setColumnCount(4)
        self._track_table.setHorizontalHeaderLabels(
            ["#", "Title", "Artist", "Length"]
        )
        self._track_table.horizontalHeader().setStretchLastSection(True)
        track_layout.addWidget(self._track_table)
        splitter.addWidget(track_group)

        layout.addWidget(splitter, 1)

        # Apply button
        btn_layout = QHBoxLayout()
        self._apply_btn = QPushButton("Apply Match")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._apply_match)
        btn_layout.addStretch()
        btn_layout.addWidget(self._apply_btn)
        layout.addLayout(btn_layout)

        # Progress
        self._progress = ProgressIndicator()
        layout.addWidget(self._progress)

    def load_files(self, paths: list[Path]) -> None:
        """Load files for auto-tagging."""
        self._files = list(paths)
        count = len(self._files)
        self._files_label.setText(f"{count} file(s) loaded for auto-tagging")
        self._search_btn.setEnabled(count > 0)
        self._search_single_btn.setEnabled(count == 1)
        self._match_list.match_model.clear()
        self._track_table.setRowCount(0)
        self._apply_btn.setEnabled(False)

        # Pre-fill hints from first file's tags
        if self._files:
            try:
                from musicorg.core.tagger import TagManager
                tm = TagManager()
                tags = tm.read(self._files[0])
                self._artist_edit.setText(tags.albumartist or tags.artist)
                self._album_edit.setText(tags.album)
            except Exception:
                pass

    def _start_search(self) -> None:
        self._do_search("album")

    def _start_search_single(self) -> None:
        self._do_search("single")

    def _do_search(self, mode: str) -> None:
        if not self._files:
            return

        self._search_btn.setEnabled(False)
        self._search_single_btn.setEnabled(False)
        self._progress.start("Searching...")

        self._search_worker = AutoTagWorker(
            paths=self._files,
            artist_hint=self._artist_edit.text().strip(),
            album_hint=self._album_edit.text().strip(),
            mode=mode,
        )
        self._search_thread = QThread()
        self._search_worker.moveToThread(self._search_thread)
        self._search_thread.started.connect(self._search_worker.run)
        self._search_worker.progress.connect(
            self._on_search_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        self._search_worker.finished.connect(self._on_search_done)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.finished.connect(self._search_thread.quit)
        self._search_worker.error.connect(self._search_thread.quit)
        self._search_thread.finished.connect(self._cleanup_search)
        self._search_thread.start()

    def _on_search_done(self, candidates: list) -> None:
        self._candidates = candidates
        self._match_list.match_model.set_candidates(candidates)
        self._search_btn.setEnabled(True)
        self._search_single_btn.setEnabled(len(self._files) == 1)
        count = len(candidates)
        self._progress.finish(f"Found {count} candidate(s)")

    def _on_search_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, message)

    def _on_search_error(self, msg: str) -> None:
        self._search_btn.setEnabled(True)
        self._search_single_btn.setEnabled(len(self._files) == 1)
        self._progress.finish(f"Error: {msg}")
        QMessageBox.critical(self, "Search Error", msg)

    def _on_match_selected(self, row: int) -> None:
        candidate = self._match_list.match_model.get_candidate(row)
        if not candidate:
            return

        self._apply_btn.setEnabled(True)

        # Show track details
        tracks = candidate.tracks
        self._track_table.setRowCount(len(tracks))
        for i, t in enumerate(tracks):
            self._track_table.setItem(i, 0, QTableWidgetItem(str(t.get("track", ""))))
            self._track_table.setItem(i, 1, QTableWidgetItem(t.get("title", "")))
            self._track_table.setItem(i, 2, QTableWidgetItem(t.get("artist", "")))
            length = t.get("length", 0)
            if length:
                mins, secs = divmod(int(length), 60)
                self._track_table.setItem(i, 3, QTableWidgetItem(f"{mins}:{secs:02d}"))
            else:
                self._track_table.setItem(i, 3, QTableWidgetItem(""))

    def _apply_match(self) -> None:
        candidate = self._match_list.selected_candidate()
        if not candidate or not self._files:
            return

        self._apply_btn.setEnabled(False)
        self._progress.start("Applying match...")

        self._apply_worker = ApplyMatchWorker(self._files, candidate)
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
        if success:
            self._progress.finish("Tags applied successfully")
            self.tags_applied.emit()
        else:
            self._progress.finish("Failed to apply tags")
        self._apply_btn.setEnabled(True)

    def _on_apply_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, message)

    def _on_apply_error(self, msg: str) -> None:
        self._progress.finish(f"Error: {msg}")
        self._apply_btn.setEnabled(True)
        QMessageBox.critical(self, "Apply Error", msg)

    def _cleanup_search(self) -> None:
        if self._search_worker:
            self._search_worker.deleteLater()
            self._search_worker = None
        if self._search_thread:
            self._search_thread.deleteLater()
            self._search_thread = None

    def _cleanup_apply(self) -> None:
        if self._apply_worker:
            self._apply_worker.deleteLater()
            self._apply_worker = None
        if self._apply_thread:
            self._apply_thread.deleteLater()
            self._apply_thread = None
