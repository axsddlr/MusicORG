"""Panel for finding and removing duplicate audio files."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from musicorg.core.duplicate_finder import DuplicateGroup
from musicorg.ui.widgets.dir_picker import DirPicker
from musicorg.ui.widgets.progress_bar import ProgressIndicator
from musicorg.workers.duplicate_worker import DuplicateDeleteWorker, DuplicateScanWorker

COLOR_KEEP = QColor("#4CAF50")
COLOR_DELETE = QColor("#F44336")
COLOR_GROUP = QColor("#d4a44a")
COLOR_MUTED = QColor("#7a8494")


def _fmt_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


class DuplicatesPanel(QWidget):
    """Panel for finding and removing duplicate audio files."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._groups: list[DuplicateGroup] = []
        self._cache_db_path: str = ""
        self._scan_worker: DuplicateScanWorker | None = None
        self._scan_thread: QThread | None = None
        self._delete_worker: DuplicateDeleteWorker | None = None
        self._delete_thread: QThread | None = None

        self._setup_ui()

    def set_cache_db_path(self, path: str) -> None:
        self._cache_db_path = path

    def set_source_dir(self, path: str) -> None:
        self._dir_picker.set_path(path)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header row
        header = QHBoxLayout()
        self._dir_picker = DirPicker("Browse...")
        header.addWidget(self._dir_picker, 1)

        self._match_artist_check = QCheckBox("Also match artist")
        header.addWidget(self._match_artist_check)

        self._scan_btn = QPushButton("Find Duplicates")
        self._scan_btn.setProperty("role", "accent")
        self._scan_btn.clicked.connect(self._start_scan)
        header.addWidget(self._scan_btn)
        layout.addLayout(header)

        # Summary label
        self._summary_label = QLabel("")
        layout.addWidget(self._summary_label)

        # Results tree
        self._tree = QTreeWidget()
        self._tree.setColumnCount(8)
        self._tree.setHeaderLabels(
            ["Action", "Title", "Artist", "Album", "Format", "Bitrate", "Size", "Path"]
        )
        tree_header = self._tree.header()
        tree_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tree_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tree_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tree_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        tree_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        tree_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        tree_header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        tree_header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(True)
        layout.addWidget(self._tree, 1)

        # Action row
        action_row = QHBoxLayout()
        self._delete_btn = QPushButton("Delete Selected")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._start_delete)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._cancel)
        action_row.addWidget(self._delete_btn)
        action_row.addWidget(self._cancel_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        # Progress
        self._progress = ProgressIndicator()
        layout.addWidget(self._progress)

    def _start_scan(self) -> None:
        if self._scan_thread and self._scan_thread.isRunning():
            QMessageBox.information(self, "Scan In Progress", "A scan is already running.")
            return

        source = self._dir_picker.path()
        if not source:
            QMessageBox.warning(self, "Missing", "Please select a directory.")
            return

        self._scan_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._tree.clear()
        self._groups = []
        self._summary_label.setText("")
        self._progress.start("Scanning for duplicates...")

        self._scan_worker = DuplicateScanWorker(
            source,
            match_artist=self._match_artist_check.isChecked(),
            cache_db_path=self._cache_db_path,
        )
        self._scan_thread = QThread()
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.progress.connect(
            self._on_scan_progress, Qt.ConnectionType.QueuedConnection
        )
        self._scan_worker.finished.connect(self._on_scan_done)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.cancelled.connect(self._on_scan_cancelled)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.error.connect(self._scan_thread.quit)
        self._scan_worker.cancelled.connect(self._scan_thread.quit)
        self._scan_thread.finished.connect(self._cleanup_scan)
        self._scan_thread.start()

    def _on_scan_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, message)

    def _on_scan_done(self, groups: list[DuplicateGroup]) -> None:
        self._groups = groups
        self._populate_tree()
        self._scan_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._delete_btn.setEnabled(bool(groups))

        total_files = sum(len(g.deletable_files) for g in groups)
        total_size = sum(f.size for g in groups for f in g.deletable_files)
        self._summary_label.setText(
            f"Found {len(groups)} groups, {total_files} files to delete, "
            f"{_fmt_size(total_size)} reclaimable"
        )
        self._progress.finish(f"Found {len(groups)} duplicate groups")

    def _on_scan_error(self, error_message: str) -> None:
        self._scan_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress.finish(f"Error: {error_message}")
        QMessageBox.critical(self, "Scan Error", error_message)

    def _on_scan_cancelled(self) -> None:
        self._scan_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress.finish("Scan cancelled")

    def _populate_tree(self) -> None:
        self._tree.clear()
        for group in self._groups:
            kept = group.kept_file
            display_title = kept.tags.title if kept else group.normalized_key

            # Group header item
            group_item = QTreeWidgetItem(self._tree)
            group_item.setText(0, f"{len(group.files)} files")
            group_item.setText(1, display_title)
            group_item.setFlags(group_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            for col in range(self._tree.columnCount()):
                group_item.setForeground(col, COLOR_GROUP)

            # Child items
            for df in group.files:
                child = QTreeWidgetItem(group_item)
                if df.keep:
                    child.setText(0, "KEEP \u2713")
                    child.setFlags(child.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                    color = COLOR_KEEP
                else:
                    child.setText(0, "DELETE")
                    child.setCheckState(0, Qt.CheckState.Checked)
                    color = COLOR_DELETE

                child.setText(1, df.tags.title)
                child.setText(2, df.tags.artist)
                child.setText(3, df.tags.album)
                child.setText(4, df.extension.upper().lstrip("."))
                child.setText(5, f"{df.bitrate // 1000} kbps" if df.bitrate else "")
                child.setText(6, _fmt_size(df.size))
                child.setText(7, str(df.path))

                for col in range(self._tree.columnCount()):
                    child.setForeground(col, color)

                child.setData(0, Qt.ItemDataRole.UserRole, str(df.path))

            group_item.setExpanded(True)

    def _get_checked_paths(self) -> list[Path]:
        """Collect paths from checked (deletable) child items."""
        paths: list[Path] = []
        for gi in range(self._tree.topLevelItemCount()):
            group_item = self._tree.topLevelItem(gi)
            for ci in range(group_item.childCount()):
                child = group_item.child(ci)
                if child.checkState(0) == Qt.CheckState.Checked:
                    path_str = child.data(0, Qt.ItemDataRole.UserRole)
                    if path_str:
                        paths.append(Path(path_str))
        return paths

    def _start_delete(self) -> None:
        paths = self._get_checked_paths()
        if not paths:
            QMessageBox.information(self, "Nothing Selected", "No files selected for deletion.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Delete {len(paths)} file(s)?\n\n"
            "Files will be sent to the recycle bin if possible.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._scan_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._progress.start("Deleting files...")

        self._delete_worker = DuplicateDeleteWorker(paths)
        self._delete_thread = QThread()
        self._delete_worker.moveToThread(self._delete_thread)
        self._delete_thread.started.connect(self._delete_worker.run)
        self._delete_worker.progress.connect(
            self._on_delete_progress, Qt.ConnectionType.QueuedConnection
        )
        self._delete_worker.finished.connect(self._on_delete_done)
        self._delete_worker.error.connect(self._on_delete_error)
        self._delete_worker.cancelled.connect(self._on_delete_cancelled)
        self._delete_worker.finished.connect(self._delete_thread.quit)
        self._delete_worker.error.connect(self._delete_thread.quit)
        self._delete_worker.cancelled.connect(self._delete_thread.quit)
        self._delete_thread.finished.connect(self._cleanup_delete)
        self._delete_thread.start()

    def _on_delete_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, message)

    def _on_delete_done(self, result: dict) -> None:
        deleted = result.get("deleted", 0)
        failed = result.get("failed", [])
        self._scan_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)

        msg = f"Deleted {deleted} file(s)"
        if failed:
            msg += f", {len(failed)} failed"
        self._progress.finish(msg)
        self._summary_label.setText(msg)

        if failed:
            detail = "\n".join(failed[:20])
            QMessageBox.warning(self, "Some Deletions Failed", detail)

    def _on_delete_error(self, error_message: str) -> None:
        self._scan_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress.finish(f"Error: {error_message}")
        QMessageBox.critical(self, "Delete Error", error_message)

    def _on_delete_cancelled(self) -> None:
        self._scan_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress.finish("Deletion cancelled")

    def _cancel(self) -> None:
        if self._scan_worker:
            self._scan_worker.cancel()
        if self._delete_worker:
            self._delete_worker.cancel()

    def _cleanup_scan(self) -> None:
        scan_worker = self._scan_worker
        scan_thread = self._scan_thread
        if scan_worker and scan_thread:
            for sig, slot in [
                (scan_worker.progress, self._on_scan_progress),
                (scan_worker.finished, self._on_scan_done),
                (scan_worker.error, self._on_scan_error),
                (scan_worker.cancelled, self._on_scan_cancelled),
                (scan_worker.finished, scan_thread.quit),
                (scan_worker.error, scan_thread.quit),
                (scan_worker.cancelled, scan_thread.quit),
            ]:
                try:
                    sig.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        if scan_worker:
            scan_worker.deleteLater()
            self._scan_worker = None
        if scan_thread:
            scan_thread.deleteLater()
            self._scan_thread = None

    def _cleanup_delete(self) -> None:
        delete_worker = self._delete_worker
        delete_thread = self._delete_thread
        if delete_worker and delete_thread:
            for sig, slot in [
                (delete_worker.progress, self._on_delete_progress),
                (delete_worker.finished, self._on_delete_done),
                (delete_worker.error, self._on_delete_error),
                (delete_worker.cancelled, self._on_delete_cancelled),
                (delete_worker.finished, delete_thread.quit),
                (delete_worker.error, delete_thread.quit),
                (delete_worker.cancelled, delete_thread.quit),
            ]:
                try:
                    sig.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        if delete_worker:
            delete_worker.deleteLater()
            self._delete_worker = None
        if delete_thread:
            delete_thread.deleteLater()
            self._delete_thread = None

    def shutdown(self, timeout_ms: int = 3000) -> None:
        if self._scan_worker:
            self._scan_worker.cancel()
        if self._delete_worker:
            self._delete_worker.cancel()
        if self._scan_thread and self._scan_thread.isRunning():
            self._scan_thread.quit()
            self._scan_thread.wait()
        if self._delete_thread and self._delete_thread.isRunning():
            self._delete_thread.quit()
            self._delete_thread.wait()
        self._cleanup_scan()
        self._cleanup_delete()
