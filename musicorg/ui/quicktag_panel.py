"""Quick Tag panel - keyboard-driven energy/mood/genre tagging."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QGroupBox, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from musicorg.core.tag_profiles import DEFAULT_QUICKTAG_PRESETS
from musicorg.ui.widgets.progress_bar import ProgressIndicator
from musicorg.ui.utils import safe_disconnect_multiple
from musicorg.workers.quicktag_worker import QuickTagWorker


class QuickTagPanel(QDialog):
    tags_applied = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Quick Tag")
        self.setMinimumSize(650, 480)
        self._files: list[Path] = []
        self._worker: QuickTagWorker | None = None
        self._thread: QThread | None = None
        self._active_presets: list[str] = []
        self._preset_buttons: dict[str, QPushButton] = {}
        self._cache_db_path = ""

        self._setup_ui()

    def load_files(self, paths: list[Path]) -> None:
        self._files = list(paths)
        self._active_presets = []
        self._update_selection_label()
        self._update_active_label()
        self._update_apply_button()

    def set_cache_db_path(self, path: str) -> None:
        self._cache_db_path = path

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
        self._cleanup_thread()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._selection_label = QLabel("No files selected")
        layout.addWidget(self._selection_label)

        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Write to field:"))
        self._target_field_combo = QComboBox()
        self._target_field_combo.addItems([
            "comment", "genre", "mood", "lyrics", "composer"
        ])
        self._target_field_combo.setCurrentText("comment")
        target_layout.addWidget(self._target_field_combo)
        target_layout.addStretch()

        self._append_checkbox = QCheckBox("Append mode")
        self._append_checkbox.setChecked(True)
        self._append_checkbox.setToolTip("Append to existing tags instead of replacing")
        target_layout.addWidget(self._append_checkbox)
        layout.addLayout(target_layout)

        preset_group = QGroupBox("Tag Presets")
        self._preset_grid = QGridLayout(preset_group)
        self._preset_grid.setSpacing(4)

        categories: dict[str, list[dict]] = {}
        for preset in DEFAULT_QUICKTAG_PRESETS:
            cat = preset.get("category", "Other")
            categories.setdefault(cat, []).append(preset)

        col = 0
        row = 0
        for cat_name, presets in categories.items():
            cat_label = QLabel(f"<b>{cat_name}</b>")
            self._preset_grid.addWidget(cat_label, row, col)
            row += 1
            for preset in presets:
                label = preset["label"]
                btn = QPushButton(label)
                btn.setCheckable(True)
                btn.setFixedHeight(28)
                btn.clicked.connect(lambda checked, l=label: self._on_preset_toggled(l, checked))
                btn.setStyleSheet(
                    "QPushButton { padding: 2px 8px; border-radius: 4px; } "
                    "QPushButton:checked { background-color: #4a9eff; color: white; }"
                )
                self._preset_buttons[label] = btn
                self._preset_grid.addWidget(btn, row, col)
                row += 1
            col += 1
            row = 0

        layout.addWidget(preset_group)

        self._active_label = QLabel("Active tags: (none)")
        self._active_label.setWordWrap(True)
        layout.addWidget(self._active_label)

        btn_layout = QHBoxLayout()
        self._clear_btn = QPushButton("Clear Selection")
        self._clear_btn.clicked.connect(self._clear_active)
        btn_layout.addWidget(self._clear_btn)
        btn_layout.addStretch()

        self._apply_btn = QPushButton("Apply Tags")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._apply_tags)
        self._apply_btn.setStyleSheet(
            "QPushButton { padding: 6px 24px; font-weight: bold; }"
        )
        btn_layout.addWidget(self._apply_btn)
        layout.addLayout(btn_layout)

        self._progress = ProgressIndicator()
        layout.addWidget(self._progress)

    def _on_preset_toggled(self, label: str, checked: bool) -> None:
        if checked:
            if label not in self._active_presets:
                self._active_presets.append(label)
        else:
            if label in self._active_presets:
                self._active_presets.remove(label)
        self._update_active_label()
        self._update_apply_button()

    def _clear_active(self) -> None:
        for label, btn in self._preset_buttons.items():
            btn.setChecked(False)
        self._active_presets = []
        self._update_active_label()
        self._update_apply_button()

    def _update_selection_label(self) -> None:
        self._selection_label.setText(f"{len(self._files)} files selected")

    def _update_active_label(self) -> None:
        if self._active_presets:
            self._active_label.setText(f"Active tags: {', '.join(self._active_presets)}")
        else:
            self._active_label.setText("Active tags: (none)")

    def _update_apply_button(self) -> None:
        self._apply_btn.setEnabled(bool(self._files and self._active_presets))

    def _apply_tags(self) -> None:
        if not self._files or not self._active_presets:
            return

        self._cleanup_thread()
        self._worker = QuickTagWorker(
            paths=self._files,
            tags_to_apply=list(self._active_presets),
            target_field=self._target_field_combo.currentText(),
            append_mode=self._append_checkbox.isChecked(),
        )
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(
            lambda c, t, m: self._progress.set_progress(c, t, m)
        )
        self._worker.finished.connect(self._on_apply_finished)
        self._worker.error.connect(self._on_apply_error)
        self._worker.cancelled.connect(self._on_apply_cancelled)
        self._thread.start()

    def _on_apply_finished(self, result: dict) -> None:
        self._cleanup_thread()
        applied = result.get("applied", 0)
        total = result.get("total", 0)
        errors = result.get("errors", [])
        self._progress.set_progress(total, total, f"Applied to {applied}/{total} files")
        self.tags_applied.emit()
        self._clear_active()

    def _on_apply_error(self, message: str) -> None:
        self._cleanup_thread()
        self._progress.set_progress(0, 1, f"Error: {message}")

    def _on_apply_cancelled(self) -> None:
        self._cleanup_thread()
        self._progress.set_progress(0, 1, "Cancelled")

    def _cleanup_thread(self) -> None:
        if self._worker is not None:
            safe_disconnect_multiple(
                (self._worker.progress, lambda c, t, m: None),
                (self._worker.finished, self._on_apply_finished),
                (self._worker.error, self._on_apply_error),
                (self._worker.cancelled, self._on_apply_cancelled),
            )
            self._worker = None
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None
