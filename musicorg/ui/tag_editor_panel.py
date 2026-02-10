"""Tab 2: View/edit ID3 tags per file."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from musicorg.core.tagger import TagData, TagManager
from musicorg.ui.widgets.progress_bar import ProgressIndicator
from musicorg.ui.widgets.tag_form import TagForm
from musicorg.workers.tag_write_worker import TagWriteWorker


class TagEditorPanel(QWidget):
    """Panel for viewing and editing ID3 tags for selected files."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._files: list[Path] = []
        self._current_index: int = -1
        self._original_tags: TagData | None = None
        self._tag_manager = TagManager()
        self._worker: TagWriteWorker | None = None
        self._thread: QThread | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Navigation
        nav_layout = QHBoxLayout()
        self._prev_btn = QPushButton("< Prev")
        self._prev_btn.clicked.connect(self._prev_file)
        self._next_btn = QPushButton("Next >")
        self._next_btn.clicked.connect(self._next_file)
        self._file_label = QLabel("No file loaded")
        self._counter_label = QLabel("")

        nav_layout.addWidget(self._prev_btn)
        nav_layout.addWidget(self._file_label, 1)
        nav_layout.addWidget(self._counter_label)
        nav_layout.addWidget(self._next_btn)
        layout.addLayout(nav_layout)

        # Tag form
        self._tag_form = TagForm()
        self._tag_form.set_enabled(False)
        layout.addWidget(self._tag_form)

        # Action buttons
        btn_layout = QHBoxLayout()
        self._save_btn = QPushButton("Save")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_tags)
        self._revert_btn = QPushButton("Revert")
        self._revert_btn.setEnabled(False)
        self._revert_btn.clicked.connect(self._revert_tags)
        self._save_all_btn = QPushButton("Save All")
        self._save_all_btn.setEnabled(False)
        self._save_all_btn.clicked.connect(self._save_all_tags)

        btn_layout.addStretch()
        btn_layout.addWidget(self._revert_btn)
        btn_layout.addWidget(self._save_btn)
        btn_layout.addWidget(self._save_all_btn)
        layout.addLayout(btn_layout)

        # Progress
        self._progress = ProgressIndicator()
        layout.addWidget(self._progress)

        layout.addStretch()

    def load_files(self, paths: list[Path]) -> None:
        """Load a list of files for editing."""
        self._files = list(paths)
        if self._files:
            self._current_index = 0
            self._load_current()
            self._save_btn.setEnabled(True)
            self._revert_btn.setEnabled(True)
            self._save_all_btn.setEnabled(len(self._files) > 1)
            self._tag_form.set_enabled(True)
        else:
            self._current_index = -1
            self._tag_form.clear()
            self._tag_form.set_enabled(False)
            self._file_label.setText("No file loaded")
            self._counter_label.clear()
            self._save_btn.setEnabled(False)
            self._revert_btn.setEnabled(False)
            self._save_all_btn.setEnabled(False)

    def _load_current(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._files):
            return
        path = self._files[self._current_index]
        self._file_label.setText(path.name)
        self._counter_label.setText(
            f"{self._current_index + 1} / {len(self._files)}"
        )
        self._prev_btn.setEnabled(self._current_index > 0)
        self._next_btn.setEnabled(self._current_index < len(self._files) - 1)

        try:
            tags = self._tag_manager.read(path)
        except Exception:
            tags = TagData()
        self._original_tags = tags
        self._tag_form.set_tags(tags)

    def _prev_file(self) -> None:
        if self._current_index > 0:
            self._current_index -= 1
            self._load_current()

    def _next_file(self) -> None:
        if self._current_index < len(self._files) - 1:
            self._current_index += 1
            self._load_current()

    def _save_tags(self) -> None:
        if self._current_index < 0:
            return
        path = self._files[self._current_index]
        tags = self._tag_form.get_tags()
        try:
            self._tag_manager.write(path, tags)
            self._original_tags = tags
            self._progress.start("Saved!")
            self._progress.finish(f"Saved tags for {path.name}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _revert_tags(self) -> None:
        if self._original_tags:
            self._tag_form.set_tags(self._original_tags)

    def _save_all_tags(self) -> None:
        """Save the current form's tags to ALL loaded files."""
        if not self._files:
            return

        reply = QMessageBox.question(
            self, "Save All",
            f"Apply current tags to all {len(self._files)} files?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        tags = self._tag_form.get_tags()
        items = [(p, tags) for p in self._files]

        self._progress.start("Saving all...")
        self._save_btn.setEnabled(False)

        self._worker = TagWriteWorker(items)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(
            self._on_save_all_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        self._worker.finished.connect(self._on_save_all_done)
        self._worker.error.connect(self._on_save_all_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _on_save_all_done(self, count: int) -> None:
        self._progress.finish(f"Saved tags to {count} files")
        self._save_btn.setEnabled(True)

    def _on_save_all_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, f"Writing: {message}")

    def _on_save_all_error(self, msg: str) -> None:
        self._progress.finish(f"Error: {msg}")
        self._save_btn.setEnabled(True)
        QMessageBox.critical(self, "Save Error", msg)

    def _cleanup_thread(self) -> None:
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if self._thread:
            self._thread.deleteLater()
            self._thread = None
