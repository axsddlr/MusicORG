"""Tab 1: Browse source directory, scan files, and explore artists/albums."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

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
        self._scanned_sizes: dict[Path, int] = {}
        self._all_rows: list[FileTableRow] = []
        self._library_index: dict[str, dict[str, list[FileTableRow]]] = {}
        self._active_artist: str = ""
        self._active_album: str = ""
        self._updating_filters = False
        self._scan_in_progress = False
        self._scan_target_path = ""
        self._last_scanned_path = ""
        self._pending_auto_scan_path = ""
        self._auto_scan_timer = QTimer(self)
        self._auto_scan_timer.setSingleShot(True)
        self._auto_scan_timer.setInterval(400)
        self._auto_scan_timer.timeout.connect(self._trigger_auto_scan)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Directory picker
        self._dir_picker = DirPicker("Browse...")
        self._dir_picker.path_changed.connect(self._on_source_path_changed)
        layout.addWidget(self._dir_picker)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)
        self._scan_btn = QPushButton("Scan")
        self._scan_btn.setProperty("role", "accent")
        self._scan_btn.clicked.connect(lambda: self._start_scan(force=True))
        self._send_to_editor_btn = QPushButton("Send to Tag Editor")
        self._send_to_editor_btn.setEnabled(False)
        self._send_to_autotag_btn = QPushButton("Send to Auto-Tag")
        self._send_to_autotag_btn.setEnabled(False)
        btn_layout.addWidget(self._scan_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self._send_to_editor_btn)
        btn_layout.addWidget(self._send_to_autotag_btn)
        layout.addLayout(btn_layout)

        # Browser layout: artists sidebar + album/track content.
        browser_splitter = QSplitter(Qt.Orientation.Horizontal)
        browser_splitter.setChildrenCollapsible(False)
        browser_splitter.setHandleWidth(2)

        artist_group = QGroupBox("Album Artist")
        artist_group.setMinimumWidth(230)
        artist_layout = QVBoxLayout(artist_group)
        artist_layout.setContentsMargins(6, 6, 6, 6)
        artist_layout.setSpacing(4)
        self._artist_list = QListWidget()
        self._artist_list.setUniformItemSizes(True)
        self._artist_list.currentItemChanged.connect(self._on_artist_changed)
        artist_layout.addWidget(self._artist_list)

        content_group = QGroupBox("Album and Tracks")
        content_layout = QVBoxLayout(content_group)
        content_layout.setContentsMargins(6, 6, 6, 6)
        content_layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)
        self._cover_label = QLabel("No Cover")
        self._cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_label.setFixedSize(144, 144)
        self._cover_label.setStyleSheet(
            "border: 1px solid #2f3743; border-radius: 6px; color: #9aa7bb;"
        )
        top_row.addWidget(self._cover_label, 0)

        meta_layout = QVBoxLayout()
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(4)
        self._album_title_label = QLabel("No album selected")
        self._album_title_label.setStyleSheet("font-size: 15pt; font-weight: 700;")
        self._album_meta_label = QLabel("Scan your library to begin browsing.")
        self._album_meta_label.setStyleSheet("color: #95a2b6;")
        album_select_row = QHBoxLayout()
        album_select_row.setContentsMargins(0, 4, 0, 0)
        album_select_row.setSpacing(6)
        album_select_row.addWidget(QLabel("Album:"))
        self._album_combo = QComboBox()
        self._album_combo.currentIndexChanged.connect(self._on_album_changed)
        album_select_row.addWidget(self._album_combo, 1)
        meta_layout.addWidget(self._album_title_label)
        meta_layout.addWidget(self._album_meta_label)
        meta_layout.addLayout(album_select_row)
        meta_layout.addStretch()
        top_row.addLayout(meta_layout, 1)
        content_layout.addLayout(top_row)

        self._file_table = FileTable()
        self._file_table.selection_changed.connect(self._on_selection_changed)
        content_layout.addWidget(self._file_table, 1)

        browser_splitter.addWidget(artist_group)
        browser_splitter.addWidget(content_group)
        browser_splitter.setStretchFactor(0, 2)
        browser_splitter.setStretchFactor(1, 8)
        browser_splitter.setSizes([250, 950])
        layout.addWidget(browser_splitter, 1)

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
        self.files_selected.emit(self._get_selected_paths() if has_selection else [])

    @staticmethod
    def _normalize_path(path: str) -> str:
        try:
            return str(Path(path).resolve())
        except Exception:
            return str(Path(path))

    def _on_source_path_changed(self, _path: str) -> None:
        self._auto_scan_timer.start()

    def _trigger_auto_scan(self) -> None:
        path = self._dir_picker.path()
        if not path or not Path(path).is_dir():
            return
        normalized = self._normalize_path(path)
        if normalized == self._last_scanned_path:
            return
        self._start_scan(force=False, suppress_errors=True)

    def _start_scan(self, force: bool = False, suppress_errors: bool = False) -> None:
        path = self._dir_picker.path()
        if not path or not Path(path).is_dir():
            if not suppress_errors:
                QMessageBox.warning(
                    self, "Invalid Directory", "Please select a valid directory."
                )
            return
        normalized = self._normalize_path(path)
        if self._scan_in_progress:
            self._pending_auto_scan_path = normalized
            return
        if not force and normalized == self._last_scanned_path:
            return

        self._scan_in_progress = True
        self._scan_target_path = normalized
        self._pending_auto_scan_path = ""
        self._scan_btn.setEnabled(False)
        self._reset_library_view()
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
        self._progress.update_progress(0, 0, "Reading tags...")

        paths = [af.path for af in audio_files]
        self._scanned_sizes = {af.path: af.size for af in audio_files}

        if not paths:
            self._progress.finish("No audio files found")
            self._scan_btn.setEnabled(True)
            self._scan_in_progress = False
            self._last_scanned_path = self._scan_target_path
            self._run_pending_auto_scan()
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
        rows: list[FileTableRow] = []
        for path, tag_data in results:
            size = self._scanned_sizes.get(path, 0)
            rows.append(FileTableRow(path=path, tags=tag_data, size=size))

        self._all_rows = rows
        self._build_library_index(rows)
        self._populate_artist_list()
        self._progress.finish(f"Found {len(rows)} files")
        self._scan_btn.setEnabled(True)
        self._scan_in_progress = False
        self._last_scanned_path = self._scan_target_path
        self._run_pending_auto_scan()

    def _build_library_index(self, rows: list[FileTableRow]) -> None:
        index: dict[str, dict[str, list[FileTableRow]]] = {}
        for row in rows:
            artist = (row.tags.albumartist or row.tags.artist or "Unknown Artist").strip()
            album = (row.tags.album or "Unknown Album").strip()
            artist_bucket = index.setdefault(artist, {})
            album_bucket = artist_bucket.setdefault(album, [])
            album_bucket.append(row)

        for albums in index.values():
            for album_rows in albums.values():
                album_rows.sort(
                    key=lambda r: (
                        9999 if r.tags.track <= 0 else r.tags.track,
                        r.filename.lower(),
                    )
                )
        self._library_index = index

    def _populate_artist_list(self) -> None:
        self._artist_list.clear()
        if not self._library_index:
            self._apply_filters()
            return

        for artist in sorted(self._library_index):
            albums = self._library_index[artist]
            album_count = len(albums)
            item = QListWidgetItem(
                f"{artist} ({album_count} album{'s' if album_count != 1 else ''})"
            )
            item.setData(Qt.ItemDataRole.UserRole, artist)
            self._artist_list.addItem(item)

        self._artist_list.setCurrentRow(0)

    def _on_artist_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        self._active_artist = ""
        if current is not None:
            self._active_artist = str(current.data(Qt.ItemDataRole.UserRole) or "")

        self._updating_filters = True
        self._album_combo.blockSignals(True)
        self._album_combo.clear()
        albums = self._library_index.get(self._active_artist, {})
        for album in sorted(albums):
            track_count = len(albums[album])
            self._album_combo.addItem(
                f"{album} ({track_count} track{'s' if track_count != 1 else ''})",
                album,
            )
        self._album_combo.blockSignals(False)
        self._updating_filters = False

        if self._album_combo.count() > 0:
            self._album_combo.setCurrentIndex(0)
            self._active_album = str(self._album_combo.currentData() or "")
            self._apply_filters()
        else:
            self._active_album = ""
            self._apply_filters()

    def _on_album_changed(self, _index: int) -> None:
        if self._updating_filters:
            return
        self._active_album = str(self._album_combo.currentData() or "")
        self._apply_filters()

    def _apply_filters(self) -> None:
        rows: list[FileTableRow] = []
        if self._active_artist:
            albums = self._library_index.get(self._active_artist, {})
            if self._active_album:
                rows = list(albums.get(self._active_album, []))
            else:
                for album_rows in albums.values():
                    rows.extend(album_rows)

        self._file_table.file_model.set_data(rows)
        self._on_selection_changed([])
        self._update_album_header(rows)
        self._update_cover(rows)

    def _update_album_header(self, rows: list[FileTableRow]) -> None:
        if not rows:
            self._album_title_label.setText("No album selected")
            self._album_meta_label.setText("Scan your library to begin browsing.")
            return
        track_count = len(rows)
        self._album_title_label.setText(self._active_album or "All Albums")
        self._album_meta_label.setText(
            f"{self._active_artist} \u2022 {track_count} track{'s' if track_count != 1 else ''}"
        )

    def _update_cover(self, rows: list[FileTableRow]) -> None:
        artwork = b""
        for row in rows:
            if row.tags.artwork_data:
                artwork = row.tags.artwork_data
                break
        if not artwork:
            self._cover_label.setPixmap(QPixmap())
            self._cover_label.setText("No Cover")
            return

        pixmap = QPixmap()
        if not pixmap.loadFromData(artwork):
            self._cover_label.setPixmap(QPixmap())
            self._cover_label.setText("No Cover")
            return

        scaled = pixmap.scaled(
            self._cover_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._cover_label.setText("")
        self._cover_label.setPixmap(scaled)

    def _reset_library_view(self) -> None:
        self._all_rows = []
        self._library_index = {}
        self._active_artist = ""
        self._active_album = ""
        self._artist_list.clear()
        self._album_combo.clear()
        self._file_table.file_model.clear()
        self._album_title_label.setText("No album selected")
        self._album_meta_label.setText("Scan your library to begin browsing.")
        self._cover_label.setPixmap(QPixmap())
        self._cover_label.setText("No Cover")
        self._on_selection_changed([])

    def _on_scan_error(self, error_msg: str) -> None:
        self._progress.finish(f"Error: {error_msg}")
        self._scan_btn.setEnabled(True)
        self._scan_in_progress = False
        QMessageBox.critical(self, "Scan Error", error_msg)
        self._run_pending_auto_scan()

    def _run_pending_auto_scan(self) -> None:
        if not self._pending_auto_scan_path:
            return
        pending = self._pending_auto_scan_path
        self._pending_auto_scan_path = ""
        if pending == self._last_scanned_path:
            return
        if not Path(pending).is_dir():
            return
        self._dir_picker.set_path(pending)
        self._start_scan(force=False, suppress_errors=True)

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
