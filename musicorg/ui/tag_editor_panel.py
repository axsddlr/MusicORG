"""Tab 2: View/edit ID3 tags per file."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from musicorg.core.tag_cache import TagCache
from musicorg.core.tagger import TagData, TagManager
from musicorg.ui.widgets.progress_bar import ProgressIndicator
from musicorg.ui.widgets.tag_form import TagForm
from musicorg.workers.tag_write_worker import TagWriteFailure, TagWriteSummary, TagWriteWorker


class TagEditorPanel(QDialog):
    """Dialog for viewing and editing ID3 tags for selected files."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tag Editor")
        self.resize(700, 550)
        self._files: list[Path] = []
        self._current_index: int = -1
        self._original_tags: TagData | None = None
        self._tag_manager = TagManager()
        self._cache_db_path = ""
        self._save_worker: TagWriteWorker | None = None
        self._save_thread: QThread | None = None

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
        self._save_btn.setProperty("role", "accent")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_tags)
        self._revert_btn = QPushButton("Revert")
        self._revert_btn.setEnabled(False)
        self._revert_btn.clicked.connect(self._revert_tags)
        self._save_all_btn = QPushButton("Save All")
        self._save_all_btn.setProperty("role", "accent")
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

    def set_cache_db_path(self, path: str) -> None:
        self._cache_db_path = path

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
        QApplication.processEvents()
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
            self._invalidate_cache_entries([path])
            self._original_tags = tags
            self._progress.start("Saved!")
            self._progress.finish(f"Saved tags for {path.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))

    def _revert_tags(self) -> None:
        if self._original_tags:
            self._tag_form.set_tags(self._original_tags)

    def _save_all_tags(self) -> None:
        """Save the current form's tags to ALL loaded files."""
        if not self._files:
            return
        if self._save_thread and self._save_thread.isRunning():
            QMessageBox.information(
                self,
                "Save In Progress",
                "A bulk save is already running.",
            )
            return

        reply = QMessageBox.question(
            self, "Save All",
            f"Apply current tags (including artwork) to all {len(self._files)} files?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        tags = self._tag_form.get_tags()
        items = [(p, tags) for p in self._files]

        self._progress.start("Saving all...")
        self._save_btn.setEnabled(False)
        self._save_all_btn.setEnabled(False)

        self._save_worker = TagWriteWorker(items, cache_db_path=self._cache_db_path)
        self._save_thread = QThread()
        self._save_worker.moveToThread(self._save_thread)
        self._save_thread.started.connect(self._save_worker.run)
        self._save_worker.progress.connect(
            self._on_save_all_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        self._save_worker.finished.connect(self._on_save_all_done)
        self._save_worker.error.connect(self._on_save_all_error)
        self._save_worker.finished.connect(self._save_thread.quit)
        self._save_worker.error.connect(self._save_thread.quit)
        self._save_thread.finished.connect(self._cleanup_thread)
        self._save_thread.start()

    def _on_save_all_done(self, payload: object) -> None:
        count, failed = self._coerce_save_summary(payload)

        if failed:
            self._progress.finish(
                f"Saved tags to {count} files ({len(failed)} failed)"
            )
            preview = "\n".join(
                f"- {path.name}: {error}" for path, error in failed[:8]
            )
            if len(failed) > 8:
                preview += f"\n... and {len(failed) - 8} more"
            QMessageBox.warning(
                self,
                "Save Warnings",
                f"Some files failed to save:\n{preview}",
            )
        else:
            self._progress.finish(f"Saved tags to {count} files")
        self._save_btn.setEnabled(True)
        self._save_all_btn.setEnabled(len(self._files) > 1)

    def _on_save_all_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, f"Writing: {message}")

    def _on_save_all_error(self, error_message: str) -> None:
        self._progress.finish(f"Error: {error_message}")
        self._save_btn.setEnabled(True)
        self._save_all_btn.setEnabled(len(self._files) > 1)
        QMessageBox.critical(self, "Save Error", error_message)

    @staticmethod
    def _coerce_save_summary(payload: object) -> tuple[int, list[TagWriteFailure]]:
        if isinstance(payload, int):
            return max(0, payload), []
        if not isinstance(payload, dict):
            return 0, []

        summary = cast(TagWriteSummary, payload)
        try:
            written_count = max(0, int(summary.get("written", 0)))
        except (TypeError, ValueError):
            written_count = 0
        failed_writes: list[TagWriteFailure] = []
        raw_failed = summary.get("failed", [])
        if isinstance(raw_failed, list):
            for item in raw_failed:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    continue
                failed_writes.append((Path(item[0]), str(item[1])))
        return written_count, failed_writes

    def _cleanup_thread(self) -> None:
        save_worker = self._save_worker
        save_thread = self._save_thread
        if save_worker and save_thread:
            try:
                save_worker.progress.disconnect(self._on_save_all_progress)
            except (RuntimeError, TypeError):
                pass
            try:
                save_worker.finished.disconnect(self._on_save_all_done)
            except (RuntimeError, TypeError):
                pass
            try:
                save_worker.error.disconnect(self._on_save_all_error)
            except (RuntimeError, TypeError):
                pass
            try:
                save_worker.finished.disconnect(save_thread.quit)
            except (RuntimeError, TypeError):
                pass
            try:
                save_worker.error.disconnect(save_thread.quit)
            except (RuntimeError, TypeError):
                pass
        if save_worker:
            save_worker.deleteLater()
            self._save_worker = None
        if save_thread:
            save_thread.deleteLater()
            self._save_thread = None

    def _invalidate_cache_entries(self, paths: list[Path]) -> None:
        if not self._cache_db_path or not paths:
            return
        cache: TagCache | None = None
        try:
            cache = TagCache(self._cache_db_path)
            cache.open()
            cache.invalidate_many(paths)
        except Exception:
            pass
        finally:
            if cache:
                try:
                    cache.close()
                except Exception:
                    pass

    def shutdown(self, timeout_ms: int = 3000) -> None:
        if self._save_worker:
            self._save_worker.cancel()
        if self._save_thread and self._save_thread.isRunning():
            self._save_thread.quit()
            self._save_thread.wait()
        self._cleanup_thread()
