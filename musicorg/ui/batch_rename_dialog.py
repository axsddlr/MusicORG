"""Dialog for previewing and applying batch file renames."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from musicorg.core.batch_rename import (
    BATCH_RENAME_METADATA_FIELDS,
    BatchRenamePreview,
    BatchRenameRule,
    RenamePreviewItem,
    build_batch_rename_preview,
)

_FIELD_LABELS = {
    "title": "Title",
    "artist": "Artist",
    "album": "Album",
    "albumartist": "Album Artist",
}


class BatchRenameDialog(QDialog):
    """Preview dialog for mass renaming selected files."""

    def __init__(self, paths: list[Path], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paths = list(paths)
        self._preview: BatchRenamePreview | None = None
        self._display_root = self._common_parent(self._paths)
        self._metadata_field_boxes: dict[str, QCheckBox] = {}
        self.setWindowTitle("Batch Rename Files")
        self.setMinimumSize(760, 560)
        self._setup_ui()
        self._refresh_preview()

    def rename_items(self) -> list[tuple[Path, Path]]:
        if self._preview is None:
            return []
        return [(item.source, item.destination) for item in self._preview.planned_items]

    def rename_rule(self) -> BatchRenameRule:
        return BatchRenameRule(
            pattern=self._pattern_input.text(),
            replacement=self._replace_input.text(),
            use_regex=self._regex_checkbox.isChecked(),
            case_sensitive=self._case_checkbox.isChecked(),
            include_extension=self._include_extension_checkbox.isChecked(),
        )

    def metadata_fields(self) -> tuple[str, ...]:
        if not self._metadata_checkbox.isChecked():
            return ()
        return tuple(
            field_name
            for field_name, checkbox in self._metadata_field_boxes.items()
            if checkbox.isChecked()
        )

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Rename the selected files by text replacement or regex. "
            "Leave Replace blank to remove a suffix."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        example = QLabel(
            "Example: Find ` - SpotubeDL.com` and leave Replace empty, or use "
            r"regex `\s+-\s+SpotubeDL\.com$` to remove it only at the end."
        )
        example.setWordWrap(True)
        example.setObjectName("StatusMuted")
        layout.addWidget(example)

        form = QWidget()
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(8)

        pattern_label = QLabel("Find")
        self._pattern_input = QLineEdit()
        self._pattern_input.setPlaceholderText(" - SpotubeDL.com")
        self._pattern_input.textChanged.connect(self._refresh_preview)
        form_layout.addWidget(pattern_label, 0, 0)
        form_layout.addWidget(self._pattern_input, 0, 1)

        replace_label = QLabel("Replace")
        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText("Leave empty to remove the matched text")
        self._replace_input.textChanged.connect(self._refresh_preview)
        form_layout.addWidget(replace_label, 1, 0)
        form_layout.addWidget(self._replace_input, 1, 1)

        self._regex_checkbox = QCheckBox("Use regex")
        self._regex_checkbox.toggled.connect(self._refresh_preview)
        self._case_checkbox = QCheckBox("Case sensitive")
        self._case_checkbox.toggled.connect(self._refresh_preview)
        self._include_extension_checkbox = QCheckBox("Include file extension")
        self._include_extension_checkbox.toggled.connect(self._refresh_preview)
        form_layout.addWidget(self._regex_checkbox, 2, 0)
        form_layout.addWidget(self._case_checkbox, 2, 1)
        form_layout.addWidget(self._include_extension_checkbox, 3, 1)

        layout.addWidget(form)

        metadata_group = QGroupBox("Also Update Metadata")
        metadata_layout = QGridLayout(metadata_group)
        self._metadata_checkbox = QCheckBox("Apply the same replacement to tag fields")
        self._metadata_checkbox.toggled.connect(self._on_metadata_toggle)
        metadata_layout.addWidget(self._metadata_checkbox, 0, 0, 1, 2)
        helper = QLabel(
            "Useful for stripping the same suffix from Title, Artist, Album, or Album Artist tags."
        )
        helper.setWordWrap(True)
        helper.setObjectName("StatusMuted")
        metadata_layout.addWidget(helper, 1, 0, 1, 2)
        for index, field_name in enumerate(BATCH_RENAME_METADATA_FIELDS):
            checkbox = QCheckBox(_FIELD_LABELS.get(field_name, field_name.title()))
            checkbox.setChecked(True)
            checkbox.setEnabled(False)
            checkbox.toggled.connect(self._refresh_preview)
            metadata_layout.addWidget(checkbox, 2 + (index // 2), index % 2)
            self._metadata_field_boxes[field_name] = checkbox
        layout.addWidget(metadata_group)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setObjectName("StatusDetail")
        layout.addWidget(self._status_label)

        self._preview_table = QTableWidget()
        self._preview_table.setColumnCount(3)
        self._preview_table.setHorizontalHeaderLabels(["Current Name", "New Name", "Folder"])
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
        rename_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if rename_button is not None:
            rename_button.setText("Apply Batch Rename")
        self._buttons.accepted.connect(self._accept_if_valid)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _on_metadata_toggle(self, checked: bool) -> None:
        for checkbox in self._metadata_field_boxes.values():
            checkbox.setEnabled(checked)
        self._refresh_preview()

    def _accept_if_valid(self) -> None:
        self._refresh_preview()
        if not self._can_apply():
            return
        self.accept()

    def _can_apply(self) -> bool:
        if self._preview is None:
            return False
        if self._preview.items:
            return True
        return bool(self.metadata_fields())

    def _refresh_preview(self) -> None:
        pattern = self._pattern_input.text()
        if not pattern:
            self._preview = None
            self._populate_preview_table(())
            self._set_status(
                f"Selected {len(self._paths)} files. Enter text or regex to preview renames.",
                is_error=False,
            )
            self._set_accept_enabled(False)
            return

        rule = self.rename_rule()
        try:
            preview = build_batch_rename_preview(self._paths, rule)
        except ValueError as exc:
            self._preview = None
            self._populate_preview_table(())
            self._set_status(str(exc), is_error=True)
            self._set_accept_enabled(False)
            return

        self._preview = preview
        self._populate_preview_table(preview.items)
        metadata_fields = self.metadata_fields()
        metadata_suffix = ""
        if metadata_fields:
            labels = ", ".join(_FIELD_LABELS[field] for field in metadata_fields)
            metadata_suffix = f" Metadata fields: {labels}."

        if not preview.items:
            if metadata_fields:
                self._set_status(
                    f"No filenames would change across {preview.total_count} selected files."
                    f" The same replacement will still be applied to metadata.{metadata_suffix}",
                    is_error=False,
                )
                self._set_accept_enabled(True)
                return
            self._set_status(
                f"No filenames would change across {preview.total_count} selected files.",
                is_error=False,
            )
            self._set_accept_enabled(False)
            return

        unchanged_suffix = ""
        if preview.unchanged_count:
            unchanged_suffix = f" ({preview.unchanged_count} unchanged names)"
        self._set_status(
            f"{len(preview.items)} files will be renamed{unchanged_suffix}.{metadata_suffix}",
            is_error=False,
        )
        self._set_accept_enabled(True)

    def _populate_preview_table(self, items: tuple[RenamePreviewItem, ...]) -> None:
        self._preview_table.setRowCount(len(items))
        for row_index, item in enumerate(items):
            current_item = QTableWidgetItem(item.source.name)
            new_item = QTableWidgetItem(item.destination.name)
            folder_item = QTableWidgetItem(self._display_parent(item.source.parent))
            self._preview_table.setItem(row_index, 0, current_item)
            self._preview_table.setItem(row_index, 1, new_item)
            self._preview_table.setItem(row_index, 2, folder_item)

    def _display_parent(self, folder: Path) -> str:
        if self._display_root is None:
            return str(folder)
        try:
            relative = folder.relative_to(self._display_root)
        except ValueError:
            return str(folder)
        if str(relative) == ".":
            return "."
        return str(relative)

    def _set_accept_enabled(self, enabled: bool) -> None:
        button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if button is not None:
            button.setEnabled(enabled)

    def _set_status(self, message: str, *, is_error: bool) -> None:
        self._status_label.setText(message)
        color = "#d76868" if is_error else ""
        self._status_label.setStyleSheet(f"color: {color};" if color else "")

    @staticmethod
    def _common_parent(paths: list[Path]) -> Path | None:
        if not paths:
            return None
        try:
            common = os.path.commonpath([str(path.parent) for path in paths])
        except ValueError:
            return None
        return Path(common)
