"""Tab 1: Browse source directory, scan files, show table."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from musicorg.core.tagger import TagData, TagManager
from musicorg.ui.models.file_table_model import FileTableRow
from musicorg.ui.widgets.dir_picker import DirPicker
from musicorg.ui.widgets.file_table import FileTable
from musicorg.ui.widgets.progress_bar import ProgressIndicator
from musicorg.workers.scan_worker import ScanWorker
from musicorg.workers.tag_read_worker import TagReadWorker


class SourcePanel(QWidget):
    """Panel for browsing source directory and scanning audio files."""

    files_selected = Signal(list)  # list[Path]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: ScanWorker | None = None
        self._thread: QThread | None = None
        self._tag_worker: TagReadWorker | None = None
        self._tag_thread: QThread | None = None
        self._scanned_files: list = []
        self._scanned_sizes: dict[Path, int] = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Directory picker
        self._dir_picker = DirPicker("Browse...")
        layout.addWidget(self._dir_picker)

        # Buttons
        btn_layout = QHBoxLayout()
        self._scan_btn = QPushButton("Scan")
        self._scan_btn.clicked.connect(self._start_scan)
        self._send_to_editor_btn = QPushButton("Send to Tag Editor")
        self._send_to_editor_btn.setEnabled(False)
        self._send_to_autotag_btn = QPushButton("Send to Auto-Tag")
        self._send_to_autotag_btn.setEnabled(False)
        btn_layout.addWidget(self._scan_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self._send_to_editor_btn)
        btn_layout.addWidget(self._send_to_autotag_btn)
        layout.addLayout(btn_layout)

        # File table
        self._file_table = FileTable()
        self._file_table.selection_changed.connect(self._on_selection_changed)
        layout.addWidget(self._file_table, 1)

        # Progress
        self._progress = ProgressIndicator()
        layout.addWidget(self._progress)

    def set_source_dir(self, path: str) -> None:
        self._dir_picker.set_path(path)

    def source_dir(self) -> str:
        return self._dir_picker.path()

    def connect_send_to_editor(self, slot) -> None:
        self._send_to_editor_btn.clicked.connect(
            lambda: slot(self._get_selected_paths())
        )

    def connect_send_to_autotag(self, slot) -> None:
        self._send_to_autotag_btn.clicked.connect(
            lambda: slot(self._get_selected_paths())
        )

    def _get_selected_paths(self) -> list[Path]:
        indices = self._file_table.selected_indices()
        return self._file_table.file_model.get_paths(indices)

    def _on_selection_changed(self, indices: list[int]) -> None:
        has_selection = len(indices) > 0
        self._send_to_editor_btn.setEnabled(has_selection)
        self._send_to_autotag_btn.setEnabled(has_selection)
        if has_selection:
            self.files_selected.emit(self._get_selected_paths())

    def _start_scan(self) -> None:
        path = self._dir_picker.path()
        if not path or not Path(path).is_dir():
            QMessageBox.warning(self, "Invalid Directory",
                                "Please select a valid directory.")
            return

        self._scan_btn.setEnabled(False)
        self._file_table.file_model.clear()
        self._progress.start("Scanning...")

        self._worker = ScanWorker(path)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(
            self._on_scan_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.error.connect(self._on_scan_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_scan_thread)
        self._thread.start()

    def _on_scan_finished(self, audio_files: list) -> None:
        self._scanned_files = audio_files
        self._progress.update_progress(0, 0, "Reading tags...")

        # Now read tags for all scanned files
        paths = [af.path for af in audio_files]
        self._scanned_sizes = {af.path: af.size for af in audio_files}

        if not paths:
            self._progress.finish("No audio files found")
            self._scan_btn.setEnabled(True)
            return

        self._tag_worker = TagReadWorker(paths)
        self._tag_thread = QThread()
        self._tag_worker.moveToThread(self._tag_thread)
        self._tag_thread.started.connect(self._tag_worker.run)
        self._tag_worker.progress.connect(
            self._on_tag_read_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        self._tag_worker.finished.connect(
            self._on_tags_read,
            Qt.ConnectionType.QueuedConnection,
        )
        self._tag_worker.error.connect(self._on_scan_error)
        self._tag_worker.finished.connect(self._tag_thread.quit)
        self._tag_worker.error.connect(self._tag_thread.quit)
        self._tag_thread.finished.connect(self._cleanup_tag_thread)
        self._tag_thread.start()

    def _on_scan_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, f"Found: {message}")

    def _on_tag_read_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, f"Reading: {message}")

    def _on_tags_read(self, results: list) -> None:
        rows = []
        for path, tag_data in results:
            size = self._scanned_sizes.get(path, 0)
            rows.append(FileTableRow(path=path, tags=tag_data, size=size))
        self._file_table.file_model.set_data(rows)
        self._progress.finish(f"Found {len(rows)} files")
        self._scan_btn.setEnabled(True)

    def _on_scan_error(self, error_msg: str) -> None:
        self._progress.finish(f"Error: {error_msg}")
        self._scan_btn.setEnabled(True)
        QMessageBox.critical(self, "Scan Error", error_msg)

    def _cleanup_scan_thread(self) -> None:
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if self._thread:
            self._thread.deleteLater()
            self._thread = None

    def _cleanup_tag_thread(self) -> None:
        if self._tag_worker:
            self._tag_worker.deleteLater()
            self._tag_worker = None
        if self._tag_thread:
            self._tag_thread.deleteLater()
            self._tag_thread = None
