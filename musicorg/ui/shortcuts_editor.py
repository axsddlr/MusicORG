"""Dialog for editing keyboard shortcuts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from musicorg.config.settings import AppSettings
    from musicorg.ui.keybindings import KeybindRegistry


class ShortcutEditorDialog(QDialog):
    """Dialog for viewing and editing keyboard shortcuts."""

    def __init__(
        self,
        registry: KeybindRegistry,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.resize(600, 450)
        self._registry = registry
        self._settings = settings
        self._overrides: dict[str, str] = dict(settings.keybind_overrides)
        self._recording_id: str | None = None
        self._setup_ui()
        self._populate()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        hint = QLabel("Click a shortcut to change it. Press Escape to clear.")
        hint.setObjectName("StatusMuted")
        layout.addWidget(hint)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Action", "Shortcut", "Category"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setAlternatingRowColors(True)
        self._table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self._table, 1)

        btn_layout = QHBoxLayout()
        reset_btn = QPushButton("Reset All to Defaults")
        reset_btn.clicked.connect(self._reset_all)
        btn_layout.addWidget(reset_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _populate(self) -> None:
        self._table.setRowCount(0)
        binds = self._registry.resolved_keybinds()
        for bind in binds:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(bind.label))
            override = self._overrides.get(bind.id, "")
            display = override or bind.sequence or "(none)"
            seq_item = QTableWidgetItem(display)
            seq_item.setData(256, bind.id)
            if override:
                seq_item.setData(257, True)
            self._table.setItem(row, 1, seq_item)
            self._table.setItem(row, 2, QTableWidgetItem(bind.category))
        self._table.resizeColumnsToContents()

    def _on_cell_clicked(self, row: int, col: int) -> None:
        if col != 1:
            return
        seq_item = self._table.item(row, 1)
        if seq_item is None:
            return
        bind_id = seq_item.data(256)
        if bind_id is None:
            return
        self._recording_id = bind_id
        seq_item.setText("Press new shortcut...")
        self._table.setCurrentCell(row, 1)
        self._table.keyPressEvent = self._make_record_handler(seq_item, bind_id)

    def _make_record_handler(self, seq_item: QTableWidgetItem, bind_id: str):
        def handler(event):
            if event.key() == Qt.Key.Key_Escape:
                seq_item.setText("(none)")
                self._overrides[bind_id] = ""
                self._recording_id = None
                self._table.keyPressEvent = None
                return
            key = event.key()
            if key in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
                return
            mods = event.modifiers()
            qt_key = int(mods) | key
            seq = QKeySequence(qt_key)
            text = seq.toString(QKeySequence.SequenceFormat.PortableText)
            if text:
                seq_item.setText(text)
                self._overrides[bind_id] = text
            self._recording_id = None
            self._table.keyPressEvent = None
        return handler

    def _reset_all(self) -> None:
        self._overrides.clear()
        self._populate()

    def _save(self) -> None:
        cleaned = {k: v for k, v in self._overrides.items() if v}
        self._settings.keybind_overrides = cleaned
        self.accept()
