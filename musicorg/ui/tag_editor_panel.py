"""Dialog for viewing/editing tags for selected files."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from musicorg.core.tag_cache import TagCache
from musicorg.core.tagger import TagData, TagManager
from musicorg.ui.widgets.progress_bar import ProgressIndicator
from musicorg.ui.widgets.tag_form import TagForm
from musicorg.workers.tag_write_worker import TagWriteFailure, TagWriteSummary, TagWriteWorker


class TagEditorPanel(QDialog):
    """Dialog for viewing and editing ID3 tags for selected files."""

    _SCALAR_FIELDS: tuple[str, ...] = (
        "title",
        "artist",
        "album",
        "albumartist",
        "track",
        "disc",
        "year",
        "genre",
        "composer",
        "comment",
        "lyrics",
    )
    _FIELD_LABELS = {
        "title": "Title",
        "artist": "Artist",
        "album": "Album",
        "albumartist": "Album Artist",
        "track": "Track #",
        "disc": "Disc #",
        "year": "Year",
        "genre": "Genre",
        "composer": "Composer",
        "comment": "Comment",
        "lyrics": "Lyrics",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tag Editor")
        self.resize(700, 550)
        self._files: list[Path] = []
        self._current_index: int = -1
        self._bulk_mode = False
        self._bulk_baseline_tags: TagData | None = None
        self._original_tags: TagData | None = None
        self._tag_manager = TagManager()
        self._cache_db_path = ""
        self._save_worker: TagWriteWorker | None = None
        self._save_thread: QThread | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

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

        self._mode_hint_label = QLabel("")
        self._mode_hint_label.setObjectName("StatusMuted")
        self._mode_hint_label.setWordWrap(True)
        layout.addWidget(self._mode_hint_label)

        self._tag_form = TagForm()
        self._tag_form.set_enabled(False)
        layout.addWidget(self._tag_form)

        btn_layout = QHBoxLayout()
        self._save_btn = QPushButton("Save")
        self._save_btn.setProperty("role", "accent")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_tags)
        self._revert_btn = QPushButton("Revert")
        self._revert_btn.setEnabled(False)
        self._revert_btn.clicked.connect(self._revert_tags)

        btn_layout.addStretch()
        btn_layout.addWidget(self._revert_btn)
        btn_layout.addWidget(self._save_btn)
        layout.addLayout(btn_layout)

        self._progress = ProgressIndicator()
        layout.addWidget(self._progress)

    def set_cache_db_path(self, path: str) -> None:
        self._cache_db_path = path

    def load_files(self, paths: list[Path]) -> None:
        """Load selected files for single-file or bulk editing."""
        self._files = list(paths)
        if not self._files:
            self._reset_empty_state()
            return

        self._bulk_mode = len(self._files) > 1
        self._save_btn.setEnabled(True)
        self._revert_btn.setEnabled(True)
        self._tag_form.set_enabled(True)
        self._current_index = 0

        if self._bulk_mode:
            self._enter_bulk_mode()
            return
        self._enter_single_mode()

    def _enter_single_mode(self) -> None:
        self._bulk_baseline_tags = None
        self._save_btn.setText("Save")
        self._save_btn.setToolTip("Save tags for the current file.")
        self._mode_hint_label.clear()
        self._set_navigation_visible(True)
        self._load_current()

    def _enter_bulk_mode(self) -> None:
        self._set_navigation_visible(False)
        self._save_btn.setText("Apply to Selected")
        self._save_btn.setToolTip("Apply changed fields to all selected files.")
        self._file_label.setText("Bulk edit selected files")
        self._counter_label.setText(f"{len(self._files)} selected")
        self._mode_hint_label.setText(
            "Only changed fields are applied across selected files. "
            "Unchanged fields stay per-track."
        )
        self._bulk_baseline_tags = self._build_bulk_baseline_tags()
        self._original_tags = self._bulk_baseline_tags
        self._tag_form.set_tags(self._bulk_baseline_tags)
        self._tag_form.mark_clean()

    def _reset_empty_state(self) -> None:
        self._current_index = -1
        self._bulk_mode = False
        self._bulk_baseline_tags = None
        self._original_tags = None
        self._tag_form.clear()
        self._tag_form.set_enabled(False)
        self._mode_hint_label.clear()
        self._file_label.setText("No file loaded")
        self._counter_label.clear()
        self._save_btn.setEnabled(False)
        self._revert_btn.setEnabled(False)
        self._save_btn.setText("Save")
        self._set_navigation_visible(True)
        self._prev_btn.setEnabled(False)
        self._next_btn.setEnabled(False)

    def _set_navigation_visible(self, visible: bool) -> None:
        self._prev_btn.setVisible(visible)
        self._next_btn.setVisible(visible)

    def _load_current(self) -> None:
        if self._bulk_mode or self._current_index < 0 or self._current_index >= len(self._files):
            return
        path = self._files[self._current_index]
        self._file_label.setText(path.name)
        self._counter_label.setText(f"{self._current_index + 1} / {len(self._files)}")
        self._prev_btn.setEnabled(self._current_index > 0)
        self._next_btn.setEnabled(self._current_index < len(self._files) - 1)

        tags = self._read_tags_safe(path)
        QApplication.processEvents()
        self._original_tags = tags
        self._tag_form.set_tags(tags)

    def _prev_file(self) -> None:
        if self._bulk_mode:
            return
        if self._current_index > 0:
            self._current_index -= 1
            self._load_current()

    def _next_file(self) -> None:
        if self._bulk_mode:
            return
        if self._current_index < len(self._files) - 1:
            self._current_index += 1
            self._load_current()

    def _save_tags(self) -> None:
        if self._current_index < 0 or not self._files:
            return
        if self._bulk_mode:
            self._apply_bulk_tags()
            return
        self._save_current_file_tags()

    def _save_current_file_tags(self) -> None:
        path = self._files[self._current_index]
        tags = self._tag_form.get_tags()
        try:
            self._tag_manager.write(path, tags)
            self._invalidate_cache_entries([path])
            self._original_tags = tags
            self._tag_form.mark_clean()
            self._progress.start("Saved!")
            self._progress.finish(f"Saved tags for {path.name}")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save tags for:\n{path}\n\nError: {exc}"
            )

    def _apply_bulk_tags(self) -> None:
        if not self._files:
            return
        if self._save_thread and self._save_thread.isRunning():
            QMessageBox.information(self, "Save In Progress", "A bulk save is already running.")
            return
        if self._bulk_baseline_tags is None:
            return

        form_tags = self._tag_form.get_tags()
        changed_fields = self._changed_scalar_fields(form_tags, self._bulk_baseline_tags)
        artwork_changed = self._tag_form.artwork_modified()
        if not changed_fields and not artwork_changed:
            QMessageBox.information(
                self,
                "No Changes",
                "Change at least one field before applying to selected files.",
            )
            return

        changed_names = [self._FIELD_LABELS[field] for field in changed_fields]
        if artwork_changed:
            changed_names.append("Artwork")
        changed_summary = ", ".join(changed_names)
        reply = QMessageBox.question(
            self,
            "Apply to Selected",
            f"Apply changed fields to {len(self._files)} files?\n\n{changed_summary}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        items = self._build_bulk_write_items(form_tags, changed_fields, artwork_changed)
        self._start_bulk_write(items)

    def _revert_tags(self) -> None:
        if self._bulk_mode:
            if self._bulk_baseline_tags is not None:
                self._tag_form.set_tags(self._bulk_baseline_tags)
                self._tag_form.mark_clean()
            return
        if self._original_tags is not None:
            self._tag_form.set_tags(self._original_tags)
            self._tag_form.mark_clean()

    def _start_bulk_write(self, items: list[tuple[Path, TagData]]) -> None:
        self._progress.start("Applying changes...")
        self._save_btn.setEnabled(False)
        self._revert_btn.setEnabled(False)

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
            self._progress.finish(f"Saved tags to {count} files ({len(failed)} failed)")
            preview = "\n".join(f"- {path.name}: {error}" for path, error in failed[:8])
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
        self._revert_btn.setEnabled(True)
        if self._bulk_mode:
            self._bulk_baseline_tags = self._tag_form.get_tags()
            self._original_tags = self._bulk_baseline_tags
            self._tag_form.mark_clean()

    def _on_save_all_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, f"Writing: {message}")

    def _on_save_all_error(self, error_message: str) -> None:
        self._progress.finish(f"Error: {error_message}")
        self._save_btn.setEnabled(True)
        self._revert_btn.setEnabled(True)
        QMessageBox.critical(
            self,
            "Save Error",
            f"Bulk save failed:\n{error_message}"
        )

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

    def _build_bulk_baseline_tags(self) -> TagData:
        all_tags = [self._read_tags_safe(path) for path in self._files]
        if not all_tags:
            return TagData()

        def common_text(getter: str) -> str:
            values = [str(getattr(tag, getter)) for tag in all_tags]
            first = values[0]
            return first if all(value == first for value in values[1:]) else ""

        def common_int(getter: str) -> int:
            values = [int(getattr(tag, getter)) for tag in all_tags]
            first = values[0]
            return first if all(value == first for value in values[1:]) else 0

        artwork_pairs = [
            (tag.artwork_data or b"", tag.artwork_mime or "")
            for tag in all_tags
        ]
        first_artwork = artwork_pairs[0]
        if all(pair == first_artwork for pair in artwork_pairs[1:]):
            artwork_data, artwork_mime = first_artwork
        else:
            artwork_data, artwork_mime = b"", ""

        return TagData(
            title=common_text("title"),
            artist=common_text("artist"),
            album=common_text("album"),
            albumartist=common_text("albumartist"),
            track=common_int("track"),
            disc=common_int("disc"),
            year=common_int("year"),
            genre=common_text("genre"),
            composer=common_text("composer"),
            artwork_data=artwork_data,
            artwork_mime=artwork_mime,
        )

    def _changed_scalar_fields(self, current: TagData, baseline: TagData) -> set[str]:
        changed: set[str] = set()
        for field_name in self._SCALAR_FIELDS:
            if getattr(current, field_name) != getattr(baseline, field_name):
                changed.add(field_name)
        return changed

    def _build_bulk_write_items(
        self,
        form_tags: TagData,
        changed_fields: set[str],
        artwork_changed: bool,
    ) -> list[tuple[Path, TagData]]:
        items: list[tuple[Path, TagData]] = []
        for path in self._files:
            current = self._read_tags_safe(path)
            merged = TagData(**current.as_dict())
            for field_name in changed_fields:
                setattr(merged, field_name, getattr(form_tags, field_name))
            if artwork_changed:
                merged.artwork_data = form_tags.artwork_data
                merged.artwork_mime = form_tags.artwork_mime
            items.append((path, merged))
        return items

    def _read_tags_safe(self, path: Path) -> TagData:
        try:
            return self._tag_manager.read(path)
        except Exception:
            return TagData()

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
        _ = timeout_ms
        if self._save_worker:
            self._save_worker.cancel()
        if self._save_thread and self._save_thread.isRunning():
            self._save_thread.quit()
            self._save_thread.wait()
        self._cleanup_thread()
