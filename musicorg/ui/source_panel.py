"""Tab 1: Browse source directory, scan files, and explore artists/albums."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidgetItem,
    QMessageBox, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from musicorg.core.tagger import TagData
from musicorg.ui.models.file_table_model import FileTableRow
from musicorg.ui.widgets.album_browser import AlbumBrowser
from musicorg.ui.widgets.alphabet_bar import AlphabetBar
from musicorg.ui.widgets.artist_list import ArtistListWidget, ROLE_ARTIST_KEY
from musicorg.ui.widgets.dir_picker import DirPicker
from musicorg.ui.widgets.progress_bar import ProgressIndicator
from musicorg.ui.widgets.selection_manager import SelectionManager
from musicorg.workers.scan_worker import ScanWorker
from musicorg.workers.tag_read_worker import (
    TagBatchEntry,
    TagReadFailure,
    TagReadFinishedPayload,
    TagReadWorker,
)


class SourcePanel(QWidget):
    """Panel for browsing source directory and scanning audio files."""

    album_artwork_changed = Signal(bytes)
    send_to_editor_requested = Signal(list)
    send_to_autotag_requested = Signal(list)
    send_to_artwork_requested = Signal(list)
    selection_stats_changed = Signal(int, int)  # total, selected

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scan_worker: ScanWorker | None = None
        self._scan_thread: QThread | None = None
        self._tag_worker: TagReadWorker | None = None
        self._tag_thread: QThread | None = None
        self._scanned_sizes: dict[Path, int] = {}
        self._cache_db_path = ""
        self._all_rows: list[FileTableRow] = []
        self._library_index: dict[str, dict[str, list[FileTableRow]]] = {}
        self._all_artists: list[str] = []
        self._artist_meta: dict[str, tuple[QPixmap, int]] = {}
        self._active_artist: str = ""
        self._scan_in_progress = False
        self._scan_target_path = ""
        self._last_scanned_path = ""
        self._pending_auto_scan_path = ""
        self._first_batch_rendered = False
        self._auto_scan_timer = QTimer(self)
        self._auto_scan_timer.setSingleShot(True)
        self._auto_scan_timer.setInterval(400)
        self._auto_scan_timer.timeout.connect(self._trigger_auto_scan)
        self._previous_scan_paths: set[Path] = set()

        self._selection_manager = SelectionManager(self)
        self._selection_manager.selection_changed.connect(self._on_selection_changed)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Directory picker
        self._dir_picker = DirPicker("Browse...")
        self._dir_picker.setMaximumHeight(32)
        self._dir_picker.path_changed.connect(self._on_source_path_changed)
        layout.addWidget(self._dir_picker)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)
        self._scan_btn = QPushButton("Scan")
        self._scan_btn.setProperty("role", "accent")
        self._scan_btn.clicked.connect(lambda: self._start_scan(force=True))
        self._select_all_btn = QPushButton("Select All")
        self._select_all_btn.setEnabled(False)
        self._select_all_btn.clicked.connect(self._select_all_visible_tracks)
        self._deselect_all_btn = QPushButton("Deselect All")
        self._deselect_all_btn.setEnabled(False)
        self._deselect_all_btn.clicked.connect(self._deselect_all_tracks)
        btn_layout.addWidget(self._scan_btn)
        btn_layout.addWidget(self._select_all_btn)
        btn_layout.addWidget(self._deselect_all_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        action_container = QWidget()
        action_container.setObjectName("SelectionActionBar")
        action_layout = QHBoxLayout(action_container)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        self._selection_status_label = QLabel("0 selected")
        self._selection_status_label.setObjectName("StatusDetail")
        self._open_editor_btn = QPushButton("Tag Editor")
        self._open_editor_btn.clicked.connect(self._send_selected_to_editor)
        self._open_autotag_btn = QPushButton("Auto-Tag")
        self._open_autotag_btn.clicked.connect(self._send_selected_to_autotag)
        self._open_artwork_btn = QPushButton("Artwork")
        self._open_artwork_btn.clicked.connect(self._send_selected_to_artwork)
        action_layout.addWidget(self._selection_status_label)
        action_layout.addStretch()
        action_layout.addWidget(self._open_editor_btn)
        action_layout.addWidget(self._open_autotag_btn)
        action_layout.addWidget(self._open_artwork_btn)
        layout.addWidget(action_container)

        # Browser layout: artists sidebar + album browser
        browser_splitter = QSplitter(Qt.Orientation.Horizontal)
        browser_splitter.setChildrenCollapsible(False)
        browser_splitter.setHandleWidth(2)

        # Left pane: artist list
        artist_pane = QWidget()
        artist_pane.setMinimumWidth(230)
        artist_layout = QVBoxLayout(artist_pane)
        artist_layout.setContentsMargins(0, 0, 0, 0)
        artist_layout.setSpacing(4)
        artist_header = QLabel("ALBUM ARTIST")
        artist_header.setObjectName("SectionHeader")
        artist_header.setContentsMargins(6, 6, 6, 2)
        artist_layout.addWidget(artist_header)
        self._artist_filter = QLineEdit()
        self._artist_filter.setPlaceholderText("Filter artists...")
        self._artist_filter.textChanged.connect(self._apply_artist_filter)
        artist_layout.addWidget(self._artist_filter)
        self._artist_list_widget = ArtistListWidget()
        self._artist_list_widget.currentItemChanged.connect(self._on_artist_changed)
        artist_layout.addWidget(self._artist_list_widget)

        # Right pane: alphabet bar + album browser
        content_pane = QWidget()
        content_layout = QVBoxLayout(content_pane)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)
        self._alphabet_bar = AlphabetBar()
        self._alphabet_bar.letter_clicked.connect(self._on_letter_clicked)
        content_layout.addWidget(self._alphabet_bar)
        self._album_browser = AlbumBrowser()
        self._album_browser.album_artwork_changed.connect(self.album_artwork_changed.emit)
        self._album_browser.send_to_editor.connect(self.send_to_editor_requested.emit)
        self._album_browser.send_to_autotag.connect(self.send_to_autotag_requested.emit)
        self._album_browser.send_to_artwork.connect(self.send_to_artwork_requested.emit)
        content_layout.addWidget(self._album_browser, 1)

        browser_splitter.addWidget(artist_pane)
        browser_splitter.addWidget(content_pane)
        browser_splitter.setStretchFactor(0, 2)
        browser_splitter.setStretchFactor(1, 8)
        browser_splitter.setSizes([250, 950])
        layout.addWidget(browser_splitter, 1)

        # Progress
        self._progress = ProgressIndicator()
        layout.addWidget(self._progress)
        self._update_selection_action_buttons()

    def set_source_dir(self, path: str) -> None:
        self._dir_picker.set_path(path)

    def source_dir(self) -> str:
        return self._dir_picker.path()

    def selected_paths(self) -> list[Path]:
        return self._selection_manager.selected_paths()

    def set_cache_db_path(self, path: str) -> None:
        self._cache_db_path = path

    def _on_selection_changed(self, _selected_paths: list[Path]) -> None:
        self._update_selection_action_buttons()

    def _visible_paths(self) -> list[Path]:
        albums = self._library_index.get(self._active_artist, {})
        return [row.path for album_rows in albums.values() for row in album_rows]

    def _update_selection_action_buttons(self) -> None:
        visible_paths = self._visible_paths()
        has_visible = bool(visible_paths)
        selected_paths = self._selection_manager.selected_paths()
        selected_count = len(selected_paths)
        has_selection = bool(selected_count)
        self._select_all_btn.setEnabled(has_visible)
        self._deselect_all_btn.setEnabled(has_visible and has_selection)
        self._open_editor_btn.setEnabled(has_selection)
        self._open_autotag_btn.setEnabled(has_selection)
        self._open_artwork_btn.setEnabled(has_selection)
        self._selection_status_label.setText(f"{selected_count} selected")
        self._emit_selection_stats()

    def _select_all_visible_tracks(self) -> None:
        visible_paths = self._visible_paths()
        if visible_paths:
            self._selection_manager.select_all(visible_paths)

    def _deselect_all_tracks(self) -> None:
        self._selection_manager.clear()

    def _send_selected_to_editor(self) -> None:
        paths = self._selection_manager.selected_paths()
        if paths:
            self.send_to_editor_requested.emit(paths)

    def _send_selected_to_autotag(self) -> None:
        paths = self._selection_manager.selected_paths()
        if paths:
            self.send_to_autotag_requested.emit(paths)

    def _send_selected_to_artwork(self) -> None:
        paths = self._selection_manager.selected_paths()
        if paths:
            self.send_to_artwork_requested.emit(paths)

    def _emit_selection_stats(self) -> None:
        self.selection_stats_changed.emit(
            len(self._all_rows),
            len(self._selection_manager.selected_paths()),
        )

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

        self._scan_worker = ScanWorker(path)
        self._scan_thread = QThread()
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.progress.connect(
            self._on_scan_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.error.connect(self._scan_thread.quit)
        self._scan_thread.finished.connect(self._cleanup_scan_thread)
        self._scan_thread.start()

    def _on_scan_finished(self, audio_files: list) -> None:
        self._progress.update_progress(0, 0, "Reading tags...")

        paths = [af.path for af in audio_files]
        mtimes_ns = [af.mtime_ns for af in audio_files]
        sizes = [af.size for af in audio_files]
        self._scanned_sizes = {af.path: af.size for af in audio_files}

        if not paths:
            self._progress.finish("No audio files found")
            self._scan_btn.setEnabled(True)
            self._scan_in_progress = False
            self._last_scanned_path = self._scan_target_path
            self._run_pending_auto_scan()
            return

        self._tag_worker = TagReadWorker(
            paths,
            sizes=sizes,
            mtimes_ns=mtimes_ns,
            cache_db_path=self._cache_db_path,
        )
        self._first_batch_rendered = False
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
        self._tag_worker.batch_ready.connect(
            self._on_tag_batch_ready,
            Qt.ConnectionType.QueuedConnection,
        )
        self._tag_worker.error.connect(self._on_scan_error)
        self._tag_worker.finished.connect(self._tag_thread.quit)
        self._tag_worker.error.connect(self._tag_thread.quit)
        self._tag_thread.finished.connect(self._cleanup_tag_thread)
        self._tag_thread.start()

    def _on_scan_progress(self, current: int, total: int, _message: str) -> None:
        self._progress.update_progress(current, total, f"Scanning... {current} files found")

    def _on_tag_read_progress(self, current: int, total: int, _message: str) -> None:
        self._progress.update_progress(current, total, f"Importing files {current}/{total}")

    def _on_tag_batch_ready(self, batch: object) -> None:
        batch_rows = self._coerce_tag_batch(batch)
        if not batch_rows:
            return
        rows: list[FileTableRow] = []
        for path_obj, tag_data in batch_rows:
            rows.append(
                FileTableRow(
                    path=path_obj,
                    tags=tag_data,
                    size=self._scanned_sizes.get(path_obj, 0),
                )
            )
        if not rows:
            return
        self._all_rows.extend(rows)
        self._merge_into_library_index(rows)
        if not self._first_batch_rendered:
            self._first_batch_rendered = True
            self._strip_redundant_artwork()
            self._populate_artist_list()

    def _on_tags_read(self, payload: object) -> None:
        failures, cache_hits, cache_misses = self._coerce_tag_read_payload(payload)

        # _all_rows and _library_index were already built incrementally
        # by _on_tag_batch_ready; just do the final artwork strip + artist
        # list refresh (which reuses cached thumbnails).
        self._strip_redundant_artwork()
        self._populate_artist_list()

        current_paths = {row.path for row in self._all_rows}
        if self._previous_scan_paths:
            new_count = len(current_paths - self._previous_scan_paths)
            if new_count > 0:
                new_label = f"{new_count} new since last scan"
            else:
                new_label = "no new files"
            summary = f"Found {len(self._all_rows)} files ({new_label})"
        else:
            summary = (
                f"Found {len(self._all_rows)} files ({cache_hits} cached, {cache_misses} read)"
            )
        self._previous_scan_paths = current_paths
        if failures:
            self._progress.finish(f"{summary}, {len(failures)} tag read errors")
            preview = "\n".join(
                f"- {path.name}: {error}" for path, error in failures[:8]
            )
            if len(failures) > 8:
                preview += f"\n... and {len(failures) - 8} more"
            QMessageBox.warning(
                self,
                "Tag Read Warnings",
                f"Some files could not be read:\n{preview}",
            )
        else:
            self._progress.finish(summary)
        self._scan_btn.setEnabled(True)
        self._scan_in_progress = False
        self._last_scanned_path = self._scan_target_path
        self._emit_selection_stats()
        self._run_pending_auto_scan()

    @staticmethod
    def _coerce_tag_batch(batch_payload: object) -> list[TagBatchEntry]:
        if not isinstance(batch_payload, list):
            return []
        batch_rows: list[TagBatchEntry] = []
        for item in batch_payload:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            path_obj = Path(item[0])
            tags = item[1] if isinstance(item[1], TagData) else None
            batch_rows.append((path_obj, tags))
        return batch_rows

    @staticmethod
    def _coerce_tag_read_payload(
        payload: object,
    ) -> tuple[list[TagReadFailure], int, int]:
        if not isinstance(payload, dict):
            return [], 0, 0
        typed_payload = cast(TagReadFinishedPayload, payload)
        cache_hits = SourcePanel._coerce_non_negative_int(
            typed_payload.get("cache_hits", 0)
        )
        cache_misses = SourcePanel._coerce_non_negative_int(
            typed_payload.get("cache_misses", 0)
        )
        failures: list[TagReadFailure] = []
        raw_failures = typed_payload.get("failures", [])
        if not isinstance(raw_failures, list):
            return failures, cache_hits, cache_misses
        for item in raw_failures:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            failures.append((Path(item[0]), str(item[1])))
        return failures, cache_hits, cache_misses

    @staticmethod
    def _coerce_non_negative_int(value: object) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

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

    def _merge_into_library_index(self, rows: list[FileTableRow]) -> None:
        affected: set[tuple[str, str]] = set()
        for row in rows:
            artist = (row.tags.albumartist or row.tags.artist or "Unknown Artist").strip()
            album = (row.tags.album or "Unknown Album").strip()
            artist_bucket = self._library_index.setdefault(artist, {})
            album_bucket = artist_bucket.setdefault(album, [])
            album_bucket.append(row)
            affected.add((artist, album))

        for artist, album in affected:
            album_rows = self._library_index[artist][album]
            album_rows.sort(
                key=lambda r: (
                    9999 if r.tags.track <= 0 else r.tags.track,
                    r.filename.lower(),
                )
            )

    def _strip_redundant_artwork(self) -> None:
        for albums in self._library_index.values():
            for album_rows in albums.values():
                kept_artwork = False
                for row in album_rows:
                    if not row.tags.artwork_data:
                        continue
                    if not kept_artwork:
                        kept_artwork = True
                        continue
                    row.tags.artwork_data = None
                    row.tags.artwork_mime = ""

    def _populate_artist_list(self) -> None:
        self._all_artists = sorted(self._library_index)
        for artist in self._all_artists:
            albums = self._library_index[artist]
            album_count = len(albums)
            existing = self._artist_meta.get(artist)
            if existing is not None:
                # Reuse cached thumbnail, just update album count
                self._artist_meta[artist] = (existing[0], album_count)
            else:
                self._artist_meta[artist] = (
                    self._build_artist_thumbnail(albums),
                    album_count,
                )
        # Remove stale entries for artists no longer in the index
        stale = self._artist_meta.keys() - set(self._all_artists)
        for key in stale:
            del self._artist_meta[key]
        self._apply_artist_filter()

    def _build_artist_thumbnail(self, albums: dict[str, list[FileTableRow]]) -> QPixmap:
        thumbnail = QPixmap()
        for album_rows in albums.values():
            for row in album_rows:
                if row.tags.artwork_data and thumbnail.loadFromData(row.tags.artwork_data):
                    return thumbnail
        return thumbnail

    def _apply_artist_filter(self) -> None:
        query = self._artist_filter.text().strip().lower()
        filtered_artists = [
            artist for artist in self._all_artists
            if not query or query in artist.lower()
        ]

        self._artist_list_widget.blockSignals(True)
        self._artist_list_widget.clear()

        available_letters: set[str] = set()
        for artist in filtered_artists:
            thumbnail, album_count = self._artist_meta.get(artist, (QPixmap(), 0))
            self._artist_list_widget.add_artist(artist, artist, thumbnail, album_count)

            first_char = artist[0].upper() if artist else "#"
            if first_char.isalpha():
                available_letters.add(first_char)
            else:
                available_letters.add("#")

        self._artist_list_widget.blockSignals(False)
        self._alphabet_bar.set_available_letters(available_letters)

        if not filtered_artists:
            self._active_artist = ""
            self._selection_manager.clear()
            self._album_browser.clear()
            self._alphabet_bar.set_active_letter("")
            self._update_selection_action_buttons()
            return

        target_artist = self._active_artist
        if target_artist not in filtered_artists:
            target_artist = filtered_artists[0]
        self._select_artist(target_artist)

    def _select_artist(self, artist_key: str) -> None:
        for i in range(self._artist_list_widget.count()):
            item = self._artist_list_widget.item(i)
            if item is None:
                continue
            if str(item.data(ROLE_ARTIST_KEY) or "") == artist_key:
                self._artist_list_widget.setCurrentItem(item)
                self._artist_list_widget.scrollToItem(item)
                return

    def _on_artist_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        self._active_artist = ""
        self._selection_manager.clear()
        self._emit_selection_stats()
        if current is not None:
            self._active_artist = str(current.data(ROLE_ARTIST_KEY) or "")

        albums = self._library_index.get(self._active_artist, {})
        self._album_browser.set_albums(albums, self._selection_manager)
        self._album_browser.scroll_to_top()
        self.emit_active_artist_artwork()

        # Update alphabet bar active letter
        if self._active_artist:
            first_char = self._active_artist[0].upper()
            if first_char.isalpha():
                self._alphabet_bar.set_active_letter(first_char)
            else:
                self._alphabet_bar.set_active_letter("#")
        else:
            self._alphabet_bar.set_active_letter("")
        self._update_selection_action_buttons()

    def emit_active_artist_artwork(self) -> None:
        albums = self._library_index.get(self._active_artist, {})
        if not albums:
            return
        from musicorg.ui.widgets.album_card import AlbumCard
        first_rows = next(iter(albums.values()))
        art = AlbumCard._find_artwork(first_rows)
        if art:
            self.album_artwork_changed.emit(art)

    def _on_letter_clicked(self, letter: str) -> None:
        """Find the first artist starting with the given letter and select it."""
        for i in range(self._artist_list_widget.count()):
            item = self._artist_list_widget.item(i)
            if item is None:
                continue
            artist_key = str(item.data(ROLE_ARTIST_KEY) or "")
            if not artist_key:
                continue
            first_char = artist_key[0].upper()
            match = (letter == "#" and not first_char.isalpha()) or first_char == letter
            if match:
                self._select_artist(artist_key)
                return

    def _reset_library_view(self) -> None:
        self._all_rows = []
        self._library_index = {}
        self._all_artists = []
        self._artist_meta = {}
        self._active_artist = ""
        self._first_batch_rendered = False
        self._artist_list_widget.clear()
        self._album_browser.clear()
        self._alphabet_bar.set_available_letters(set())
        self._alphabet_bar.set_active_letter("")
        self._selection_manager.clear()

    def _on_scan_error(self, error_message: str) -> None:
        self._progress.finish(f"Error: {error_message}")
        self._scan_btn.setEnabled(True)
        self._scan_in_progress = False
        QMessageBox.critical(self, "Scan Error", error_message)
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
        scan_worker = self._scan_worker
        scan_thread = self._scan_thread
        if scan_worker and scan_thread:
            try:
                scan_worker.progress.disconnect(self._on_scan_progress)
            except (RuntimeError, TypeError):
                pass
            try:
                scan_worker.finished.disconnect(self._on_scan_finished)
            except (RuntimeError, TypeError):
                pass
            try:
                scan_worker.error.disconnect(self._on_scan_error)
            except (RuntimeError, TypeError):
                pass
            try:
                scan_worker.finished.disconnect(scan_thread.quit)
            except (RuntimeError, TypeError):
                pass
            try:
                scan_worker.error.disconnect(scan_thread.quit)
            except (RuntimeError, TypeError):
                pass
        if scan_worker:
            scan_worker.deleteLater()
            self._scan_worker = None
        if scan_thread:
            scan_thread.deleteLater()
            self._scan_thread = None

    def _cleanup_tag_thread(self) -> None:
        tag_read_worker = self._tag_worker
        tag_read_thread = self._tag_thread
        if tag_read_worker and tag_read_thread:
            try:
                tag_read_worker.progress.disconnect(self._on_tag_read_progress)
            except (RuntimeError, TypeError):
                pass
            try:
                tag_read_worker.finished.disconnect(self._on_tags_read)
            except (RuntimeError, TypeError):
                pass
            try:
                tag_read_worker.batch_ready.disconnect(self._on_tag_batch_ready)
            except (RuntimeError, TypeError):
                pass
            try:
                tag_read_worker.error.disconnect(self._on_scan_error)
            except (RuntimeError, TypeError):
                pass
            try:
                tag_read_worker.finished.disconnect(tag_read_thread.quit)
            except (RuntimeError, TypeError):
                pass
            try:
                tag_read_worker.error.disconnect(tag_read_thread.quit)
            except (RuntimeError, TypeError):
                pass
        if tag_read_worker:
            tag_read_worker.deleteLater()
            self._tag_worker = None
        if tag_read_thread:
            tag_read_thread.deleteLater()
            self._tag_thread = None

    def shutdown(self, timeout_ms: int = 3000) -> None:
        self._auto_scan_timer.stop()
        if self._scan_worker:
            self._scan_worker.cancel()
        if self._tag_worker:
            self._tag_worker.cancel()
        if self._scan_thread and self._scan_thread.isRunning():
            self._scan_thread.quit()
            self._scan_thread.wait()
        if self._tag_thread and self._tag_thread.isRunning():
            self._tag_thread.quit()
            self._tag_thread.wait()
        self._cleanup_scan_thread()
        self._cleanup_tag_thread()
