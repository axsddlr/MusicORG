"""Dialog for template-based file rename using tag variables."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from musicorg.core.template_rename import build_template_rename, TemplateRenameItem


class TemplateRenameDialog(QDialog):
    def __init__(self, paths: list[Path], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paths = list(paths)
        self._items: list[TemplateRenameItem] = []
        self.setWindowTitle("Rename Files to Match Tags")
        self.setMinimumSize(760, 500)
        self._setup_ui()
        self._refresh_preview()

    def rename_items(self) -> list[tuple[Path, Path]]:
        return [(item.source, item.destination) for item in self._items]

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Generate filenames from tag values. Use variables like "
            "$artist, $title, $album, $track, $disc, $year, $genre."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        examples = QLabel(
            "Examples: $track $title | $artist - $title | $track - $title ($year)"
        )
        examples.setWordWrap(True)
        examples.setObjectName("StatusMuted")
        layout.addWidget(examples)

        form = QWidget()
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(8)

        tmpl_label = QLabel("Filename Template:")
        self._template_input = QLineEdit()
        self._template_input.setPlaceholderText("$track $title")
        self._template_input.setText("$track $title")
        self._template_input.textChanged.connect(self._refresh_preview)
        form_layout.addWidget(tmpl_label, 0, 0)
        form_layout.addWidget(self._template_input, 0, 1)
        layout.addWidget(form)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setObjectName("StatusDetail")
        layout.addWidget(self._status_label)

        self._preview_table = QTableWidget()
        self._preview_table.setColumnCount(3)
        self._preview_table.setHorizontalHeaderLabels(["Current", "New Name", "Folder"])
        self._preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._preview_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._preview_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._preview_table.verticalHeader().setVisible(False)
        header = self._preview_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._preview_table, 1)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setText("Apply Rename")
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _on_accept(self) -> None:
        if not self._items:
            return
        self.accept()

    def _refresh_preview(self) -> None:
        template = self._template_input.text().strip()
        if not template:
            self._items = []
            self._populate_table()
            self._set_status(f"Enter a template to preview renames for {len(self._paths)} files.", False)
            return

        try:
            self._items = build_template_rename(self._paths, template, sanitize=True)
        except ValueError as exc:
            self._items = []
            self._populate_table()
            self._set_status(str(exc), is_error=True)
            return

        self._populate_table()
        if self._items:
            self._set_status(f"{len(self._items)} files will be renamed.", False)
        else:
            self._set_status("No files would be renamed with this template.", False)

    def _populate_table(self) -> None:
        self._preview_table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            self._preview_table.setItem(row, 0, QTableWidgetItem(item.source.name))
            self._preview_table.setItem(row, 1, QTableWidgetItem(item.new_name))
            rel = str(item.source.parent)
            self._preview_table.setItem(row, 2, QTableWidgetItem(rel))

    def _set_status(self, message: str, *, is_error: bool) -> None:
        self._status_label.setText(message)
        color = "#d76868" if is_error else ""
        self._status_label.setStyleSheet(f"color: {color};" if color else "")
