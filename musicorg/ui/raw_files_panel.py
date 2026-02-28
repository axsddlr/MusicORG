"""Panel for browsing raw audio files in filesystem order."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from musicorg.core.scanner import AudioFile
from musicorg.ui.widgets.dir_picker import DirPicker
from musicorg.ui.widgets.progress_bar import ProgressIndicator
from musicorg.ui.utils import safe_disconnect_multiple
from musicorg.workers.scan_worker import ScanWorker

PATH_ROLE = int(Qt.ItemDataRole.UserRole)
ITEM_KIND_ROLE = PATH_ROLE + 1
ITEM_KIND_FILE = "file"
ITEM_KIND_FOLDER = "folder"


def _fmt_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


class RawFilesPanel(QWidget):
    """Filesystem-style browser for raw audio files."""

    send_to_editor_requested = Signal(list)
    send_to_autotag_requested = Signal(list)
    send_to_artwork_requested = Signal(list)
    selection_stats_changed = Signal(int, int)  # total, selected

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache_db_path = ""
        self._scan_worker: ScanWorker | None = None
        self._scan_thread: QThread | None = None
        self._scan_in_progress = False
        self._scan_target_path = ""
        self._last_scanned_path = ""
        self._pending_auto_scan_path = ""
        self._all_files: list[AudioFile] = []
        self._ordered_paths: list[Path] = []
        self._order_index: dict[Path, int] = {}
        self._file_items: list[QTreeWidgetItem] = []
        self._auto_scan_timer = QTimer(self)
        self._auto_scan_timer.setSingleShot(True)
        self._auto_scan_timer.setInterval(400)
        self._auto_scan_timer.timeout.connect(self._trigger_auto_scan)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self._dir_picker = DirPicker("Browse...")
        self._dir_picker.setMaximumHeight(32)
        self._dir_picker.path_changed.connect(self._on_source_path_changed)
        layout.addWidget(self._dir_picker)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)
        self._scan_btn = QPushButton("Load Files")
        self._scan_btn.setProperty("role", "accent")
        self._scan_btn.clicked.connect(lambda: self._start_scan(force=True))
        self._select_all_btn = QPushButton("Select All")
        self._select_all_btn.setEnabled(False)
        self._select_all_btn.clicked.connect(self._select_all_files)
        self._deselect_all_btn = QPushButton("Deselect All")
        self._deselect_all_btn.setEnabled(False)
        self._deselect_all_btn.clicked.connect(self._deselect_all_files)
        self._expand_all_btn = QPushButton("Expand All")
        self._expand_all_btn.setEnabled(False)
        self._expand_all_btn.clicked.connect(lambda: self._tree.expandAll())
        self._collapse_all_btn = QPushButton("Collapse All")
        self._collapse_all_btn.setEnabled(False)
        self._collapse_all_btn.clicked.connect(lambda: self._tree.collapseAll())
        button_row.addWidget(self._scan_btn)
        button_row.addWidget(self._select_all_btn)
        button_row.addWidget(self._deselect_all_btn)
        button_row.addWidget(self._expand_all_btn)
        button_row.addWidget(self._collapse_all_btn)
        button_row.addStretch()
        layout.addLayout(button_row)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        self._selection_label = QLabel("0 selected")
        self._selection_label.setObjectName("StatusDetail")
        action_row.addWidget(self._selection_label)
        self._deselect_selection_btn = QPushButton("Deselect")
        self._deselect_selection_btn.setEnabled(False)
        self._deselect_selection_btn.clicked.connect(self._deselect_all_files)
        action_row.addWidget(self._deselect_selection_btn)
        action_row.addStretch()
        self._editor_btn = QPushButton("Tag Editor")
        self._editor_btn.setEnabled(False)
        self._editor_btn.clicked.connect(self._send_selection_to_editor)
        self._autotag_btn = QPushButton("Auto-Tag")
        self._autotag_btn.setEnabled(False)
        self._autotag_btn.clicked.connect(self._send_selection_to_autotag)
        self._artwork_btn = QPushButton("Artwork")
        self._artwork_btn.setEnabled(False)
        self._artwork_btn.clicked.connect(self._send_selection_to_artwork)
        action_row.addWidget(self._editor_btn)
        action_row.addWidget(self._autotag_btn)
        action_row.addWidget(self._artwork_btn)
        layout.addLayout(action_row)

        hint_label = QLabel(
            "Ctrl+Click toggles; Shift+Click selects range. Right-click folders to tag all nested files."
        )
        hint_label.setObjectName("StatusMuted")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        self._tree = QTreeWidget()
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["Name", "Format", "Size", "Folder"])
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._tree, 1)

        self._progress = ProgressIndicator()
        layout.addWidget(self._progress)
        self._emit_selection_stats()

    def set_source_dir(self, path: str) -> None:
        self._dir_picker.set_path(path)

    def source_dir(self) -> str:
        return self._dir_picker.path()

    def set_cache_db_path(self, path: str) -> None:
        self._cache_db_path = path

    def selected_paths(self) -> list[Path]:
        selected: list[Path] = []
        seen: set[Path] = set()
        for item in self._tree.selectedItems():
            path = self._item_path(item)
            if path is None or path in seen:
                continue
            seen.add(path)
            selected.append(path)
        selected.sort(key=lambda path: self._order_index.get(path, len(self._ordered_paths)))
        return selected

    def _select_all_files(self) -> None:
        if not self._file_items:
            return
        self._tree.blockSignals(True)
        self._tree.clearSelection()
        for item in self._file_items:
            item.setSelected(True)
        self._tree.blockSignals(False)
        self._on_selection_changed()

    def select_all_visible(self) -> None:
        """Public method to select all visible files (for keyboard shortcut)."""
        self._select_all_files()

    def _deselect_all_files(self) -> None:
        self._tree.clearSelection()

    def _send_selection_to_editor(self) -> None:
        paths = self.selected_paths()
        if paths:
            self.send_to_editor_requested.emit(paths)

    def _send_selection_to_autotag(self) -> None:
        paths = self.selected_paths()
        if paths:
            self.send_to_autotag_requested.emit(paths)

    def _send_selection_to_artwork(self) -> None:
        paths = self.selected_paths()
        if paths:
            self.send_to_artwork_requested.emit(paths)

    def _show_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        paths = self._resolve_context_paths(item)
        if not paths:
            return

        menu = QMenu(self)
        menu.addAction(
            f"Tag Editor ({len(paths)} files)",
            lambda: self.send_to_editor_requested.emit(paths),
        )
        menu.addAction(
            f"Auto-Tag ({len(paths)} files)",
            lambda: self.send_to_autotag_requested.emit(paths),
        )
        menu.addAction(
            f"Artwork Downloader ({len(paths)} files)",
            lambda: self.send_to_artwork_requested.emit(paths),
        )
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _resolve_context_paths(self, item: QTreeWidgetItem | None) -> list[Path]:
        selected_paths = self.selected_paths()
        if item is None:
            return selected_paths

        item_kind = self._item_kind(item)
        if item_kind == ITEM_KIND_FOLDER:
            return self._paths_under_folder_item(item)

        item_path = self._item_path(item)
        if item_path is None:
            return selected_paths
        if selected_paths and item_path in selected_paths:
            return selected_paths
        return [item_path]

    def _paths_under_folder_item(self, folder_item: QTreeWidgetItem) -> list[Path]:
        paths: list[Path] = []
        seen: set[Path] = set()
        stack = [folder_item]
        while stack:
            current = stack.pop()
            child_count = current.childCount()
            for index in range(child_count):
                child = current.child(index)
                child_kind = self._item_kind(child)
                if child_kind == ITEM_KIND_FOLDER:
                    stack.append(child)
                    continue
                child_path = self._item_path(child)
                if child_path is None or child_path in seen:
                    continue
                seen.add(child_path)
                paths.append(child_path)
        return self._sorted_paths(paths)

    def _sorted_paths(self, paths: list[Path]) -> list[Path]:
        return sorted(
            paths,
            key=lambda path: (
                self._order_index.get(path, len(self._ordered_paths)),
                str(path).lower(),
            ),
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
                    self,
                    "Invalid Directory",
                    "Please select a valid directory.",
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
        self._progress.start("Scanning raw files...")
        self._reset_view()

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
        self._scan_worker.cancelled.connect(self._on_scan_cancelled)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.error.connect(self._scan_thread.quit)
        self._scan_worker.cancelled.connect(self._scan_thread.quit)
        self._scan_thread.finished.connect(self._cleanup_scan_thread)
        self._scan_thread.start()

    def _on_scan_progress(self, current: int, total: int, _message: str) -> None:
        self._progress.update_progress(current, total, f"Scanning... {current} files found")

    def _on_scan_finished(self, audio_files: list) -> None:
        self._all_files = sorted(
            audio_files,
            key=lambda af: (str(af.path.parent).lower(), af.path.name.lower()),
        )
        self._ordered_paths = [audio_file.path for audio_file in self._all_files]
        self._order_index = {
            path: index for index, path in enumerate(self._ordered_paths)
        }
        self._populate_tree()
        self._scan_btn.setEnabled(True)
        self._scan_in_progress = False
        self._last_scanned_path = self._scan_target_path
        self._update_controls()
        self._emit_selection_stats()
        self._progress.finish(f"Loaded {len(self._all_files)} audio files")
        self._run_pending_auto_scan()

    def _on_scan_error(self, error_message: str) -> None:
        self._scan_btn.setEnabled(True)
        self._scan_in_progress = False
        self._progress.finish(f"Error: {error_message}")
        QMessageBox.critical(self, "Scan Error", error_message)
        self._run_pending_auto_scan()

    def _on_scan_cancelled(self) -> None:
        self._scan_btn.setEnabled(True)
        self._scan_in_progress = False
        self._progress.finish("Scan cancelled")

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

    def _populate_tree(self) -> None:
        self._tree.clear()
        self._file_items = []
        root_path = Path(self._dir_picker.path())
        root_label = root_path.name or str(root_path)
        root_item = QTreeWidgetItem(self._tree, [root_label, "", "", str(root_path)])
        root_item.setData(0, PATH_ROLE, str(root_path))
        root_item.setData(0, ITEM_KIND_ROLE, ITEM_KIND_FOLDER)
        root_item.setFlags(root_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        root_item.setExpanded(True)
        folder_items: dict[Path, QTreeWidgetItem] = {root_path: root_item}

        for audio_file in self._all_files:
            parent_item = self._ensure_folder_item(
                audio_file.path.parent,
                root_path,
                folder_items,
            )
            file_item = QTreeWidgetItem(parent_item)
            file_item.setText(0, audio_file.path.name)
            file_item.setText(1, audio_file.extension.upper().lstrip("."))
            file_item.setText(2, _fmt_size(audio_file.size))
            file_item.setText(
                3,
                self._relative_folder(audio_file.path.parent, root_path),
            )
            file_item.setData(0, PATH_ROLE, str(audio_file.path))
            file_item.setData(0, ITEM_KIND_ROLE, ITEM_KIND_FILE)
            self._file_items.append(file_item)

        self._tree.expandToDepth(1)

    def _ensure_folder_item(
        self,
        folder_path: Path,
        root_path: Path,
        folder_items: dict[Path, QTreeWidgetItem],
    ) -> QTreeWidgetItem:
        existing = folder_items.get(folder_path)
        if existing is not None:
            return existing

        if folder_path == root_path:
            return folder_items[root_path]
        if folder_path.parent == folder_path:
            return folder_items[root_path]

        parent_item = self._ensure_folder_item(folder_path.parent, root_path, folder_items)
        folder_item = QTreeWidgetItem(parent_item)
        folder_item.setText(0, folder_path.name or str(folder_path))
        folder_item.setText(3, self._relative_folder(folder_path, root_path))
        folder_item.setData(0, PATH_ROLE, str(folder_path))
        folder_item.setData(0, ITEM_KIND_ROLE, ITEM_KIND_FOLDER)
        folder_item.setFlags(folder_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        folder_items[folder_path] = folder_item
        return folder_item

    @staticmethod
    def _relative_folder(path: Path, root: Path) -> str:
        try:
            relative = path.relative_to(root)
            if str(relative) == ".":
                return "."
            return str(relative)
        except ValueError:
            return str(path)

    @staticmethod
    def _item_kind(item: QTreeWidgetItem | None) -> str:
        if item is None:
            return ""
        kind = item.data(0, ITEM_KIND_ROLE)
        if not kind:
            return ""
        return str(kind)

    @staticmethod
    def _item_path(item: QTreeWidgetItem | None) -> Path | None:
        if item is None:
            return None
        raw_path = item.data(0, PATH_ROLE)
        if not raw_path:
            return None
        return Path(str(raw_path))

    def _on_selection_changed(self) -> None:
        selected = len(self.selected_paths())
        self._selection_label.setText(f"{selected} selected")
        self._update_controls()
        self._emit_selection_stats()

    def _update_controls(self) -> None:
        has_files = bool(self._file_items)
        selected_count = len(self.selected_paths())
        has_selection = selected_count > 0
        self._select_all_btn.setEnabled(has_files)
        self._deselect_all_btn.setEnabled(has_selection)
        self._deselect_selection_btn.setEnabled(has_selection)
        self._expand_all_btn.setEnabled(has_files)
        self._collapse_all_btn.setEnabled(has_files)
        self._editor_btn.setEnabled(has_selection)
        self._autotag_btn.setEnabled(has_selection)
        self._artwork_btn.setEnabled(has_selection)

    def _emit_selection_stats(self) -> None:
        self.selection_stats_changed.emit(len(self._ordered_paths), len(self.selected_paths()))

    def _reset_view(self) -> None:
        self._all_files = []
        self._ordered_paths = []
        self._order_index = {}
        self._file_items = []
        self._tree.clear()
        self._selection_label.setText("0 selected")
        self._update_controls()
        self._emit_selection_stats()

    def _cleanup_scan_thread(self) -> None:
        scan_worker = self._scan_worker
        scan_thread = self._scan_thread
        if scan_worker and scan_thread:
            safe_disconnect_multiple([
                (scan_worker.progress, self._on_scan_progress),
                (scan_worker.finished, self._on_scan_finished),
                (scan_worker.error, self._on_scan_error),
                (scan_worker.cancelled, self._on_scan_cancelled),
                (scan_worker.finished, scan_thread.quit),
                (scan_worker.error, scan_thread.quit),
                (scan_worker.cancelled, scan_thread.quit),
            ])
        if scan_worker:
            scan_worker.deleteLater()
            self._scan_worker = None
        if scan_thread:
            scan_thread.deleteLater()
            self._scan_thread = None

    def shutdown(self, timeout_ms: int = 3000) -> None:
        _ = timeout_ms
        self._auto_scan_timer.stop()
        if self._scan_worker:
            self._scan_worker.cancel()
        if self._scan_thread and self._scan_thread.isRunning():
            self._scan_thread.quit()
            self._scan_thread.wait()
        self._cleanup_scan_thread()
