"""Dialog for batch tag operations: find-and-replace, regex, case transform."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from musicorg.core.tagger import TagData, TagManager
from musicorg.ui.utils import safe_disconnect_multiple
from musicorg.ui.widgets.progress_bar import ProgressIndicator
from musicorg.workers.tag_write_worker import TagWriteWorker

SCALAR_FIELDS = [
    "title", "artist", "album", "albumartist",
    "genre", "composer", "comment", "lyrics",
]


class BatchMetadataDialog(QDialog):
    """Batch tag operations: find-and-replace, regex, case transform."""

    def __init__(self, paths: list[Path], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Batch Tag Operations")
        self.resize(700, 500)
        self._paths = list(paths)
        self._tag_manager = TagManager()
        self._save_worker: TagWriteWorker | None = None
        self._save_thread: QThread | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Config form
        form = QFormLayout()

        self._field_combo = QComboBox()
        for f in SCALAR_FIELDS:
            self._field_combo.addItem(f.capitalize(), f)
        form.addRow("Field:", self._field_combo)

        self._op_combo = QComboBox()
        self._op_combo.addItems(["Find & Replace", "Regex Replace", "Uppercase", "Lowercase", "Title Case", "Trim", "Clear"])
        self._op_combo.currentTextChanged.connect(self._on_op_changed)
        form.addRow("Operation:", self._op_combo)

        self._find_label = QLabel("Find:")
        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText("Text to find...")
        form.addRow(self._find_label, self._find_input)

        self._replace_label = QLabel("Replace:")
        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText("Replacement text...")
        form.addRow(self._replace_label, self._replace_input)

        self._dry_run_check = QCheckBox("Preview only (don't apply)")
        self._dry_run_check.setChecked(True)
        form.addRow(self._dry_run_check)

        layout.addLayout(form)

        # Preview table
        self._preview_table = QTableWidget(0, 3)
        self._preview_table.setHorizontalHeaderLabels(["Path", "Field", "Current → New"])
        self._preview_table.horizontalHeader().setStretchLastSection(True)
        self._preview_table.setAlternatingRowColors(True)
        layout.addWidget(self._preview_table, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        self._preview_btn = QPushButton("Preview")
        self._preview_btn.clicked.connect(self._preview)
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setProperty("role", "accent")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._apply)
        btn_layout.addWidget(self._preview_btn)
        btn_layout.addWidget(self._apply_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._progress = ProgressIndicator()
        layout.addWidget(self._progress)

    def _on_op_changed(self, op: str) -> None:
        needs_find = op in ("Find & Replace", "Regex Replace")
        needs_replace = op in ("Find & Replace", "Regex Replace")
        self._find_label.setVisible(needs_find)
        self._find_input.setVisible(needs_find)
        self._replace_label.setVisible(needs_replace)
        self._replace_input.setVisible(needs_replace)
        self._apply_btn.setEnabled(False)
        self._preview_table.setRowCount(0)

    def _transform_value(self, value: str, op: str, find: str, replace: str) -> str:
        if not value:
            return value
        if op == "Find & Replace":
            return value.replace(find, replace)
        elif op == "Regex Replace":
            try:
                return re.sub(find, replace, value)
            except re.error:
                return value
        elif op == "Uppercase":
            return value.upper()
        elif op == "Lowercase":
            return value.lower()
        elif op == "Title Case":
            return value.title()
        elif op == "Trim":
            return value.strip()
        elif op == "Clear":
            return ""
        return value

    def _preview(self) -> None:
        field_key = self._field_combo.currentData()
        op = self._op_combo.currentText()
        find = self._find_input.text()
        replace = self._replace_input.text()

        self._preview_table.setRowCount(0)
        changed_count = 0

        for path in self._paths:
            tags = self._read_tags(path)
            if tags is None:
                continue
            current = getattr(tags, field_key, "")
            new = self._transform_value(str(current), op, find, replace)
            if new != current:
                row = self._preview_table.rowCount()
                self._preview_table.insertRow(row)
                self._preview_table.setItem(row, 0, QTableWidgetItem(path.name))
                self._preview_table.setItem(row, 1, QTableWidgetItem(field_key))
                self._preview_table.setItem(row, 2, QTableWidgetItem(f"{current} → {new}"))
                changed_count += 1

        self._apply_btn.setEnabled(changed_count > 0 and not self._dry_run_check.isChecked())
        if changed_count == 0:
            self._apply_btn.setEnabled(False)

    def _apply(self) -> None:
        field_key = self._field_combo.currentData()
        op = self._op_combo.currentText()
        find = self._find_input.text()
        replace = self._replace_input.text()

        write_items: list[tuple[Path, TagData]] = []
        for path in self._paths:
            tags = self._read_tags(path)
            if tags is None:
                continue
            current = getattr(tags, field_key, "")
            new = self._transform_value(str(current), op, find, replace)
            if new != current:
                merged = TagData(**tags.as_dict())
                setattr(merged, field_key, new)
                write_items.append((path, merged))

        if not write_items:
            return

        self._preview_btn.setEnabled(False)
        self._apply_btn.setEnabled(False)
        self._progress.start(f"Applying to {len(write_items)} files...")

        self._save_worker = TagWriteWorker(write_items)
        self._save_thread = QThread()
        self._save_worker.moveToThread(self._save_thread)
        self._save_thread.started.connect(self._save_worker.run)
        self._save_worker.progress.connect(
            lambda c, t, m: self._progress.update_progress(c, t, m),
            Qt.ConnectionType.QueuedConnection,
        )
        self._save_worker.finished.connect(self._on_save_done)
        self._save_worker.error.connect(self._on_save_error)
        self._save_worker.finished.connect(self._save_thread.quit)
        self._save_worker.error.connect(self._save_thread.quit)
        self._save_thread.finished.connect(self._cleanup_save_thread)
        self._save_thread.start()

    def _on_save_done(self, summary: object) -> None:
        if isinstance(summary, dict):
            written = summary.get("written", 0)
            failed = summary.get("failed", [])
            msg = f"Updated {written} files."
            if failed:
                msg += f" {len(failed)} errors."
            self._progress.finish(msg)
            if failed:
                details = "\n".join(f"- {p.name}: {e}" for p, e in failed[:5])
                QMessageBox.warning(self, "Batch Tag Results", f"{msg}\n\nErrors:\n{details}")
        accept = len(self._paths) - (summary.get("failed", []) if isinstance(summary, dict) else 0) > 0
        self._preview_btn.setEnabled(True)
        if accept:
            self.accept()

    def _on_save_error(self, msg: str) -> None:
        self._progress.finish(f"Error: {msg}")
        self._preview_btn.setEnabled(True)

    def _cleanup_save_thread(self) -> None:
        safe_disconnect_multiple([
            (self._save_worker.progress, None),
            (self._save_worker.finished, self._on_save_done),
            (self._save_worker.error, self._on_save_error),
            (self._save_worker.finished, self._save_thread.quit),
            (self._save_worker.error, self._save_thread.quit),
        ])
        if self._save_worker:
            self._save_worker.deleteLater()
            self._save_worker = None
        if self._save_thread:
            self._save_thread.deleteLater()
            self._save_thread = None

    def _read_tags(self, path: Path) -> TagData | None:
        try:
            return self._tag_manager.read(path)
        except Exception:
            return None
