"""Keyboard shortcuts reference dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from musicorg.ui.keybindings import (
    AlbumArtworkSelectionMode,
    DEFAULT_ALBUM_ARTWORK_SELECTION_MODE,
    KeybindRegistry,
    selection_behavior_rows,
)


class ShortcutsDialog(QDialog):
    """Read-only in-app reference for keybinds and selection behavior."""

    def __init__(
        self,
        keybinds: KeybindRegistry,
        album_artwork_selection_mode: AlbumArtworkSelectionMode = (
            DEFAULT_ALBUM_ARTWORK_SELECTION_MODE
        ),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(620, 420)
        self._keybinds = keybinds
        self._album_artwork_selection_mode = album_artwork_selection_mode
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel("Use these shortcuts and selection modifiers throughout the app.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        shortcuts_group = QGroupBox("Shortcuts")
        shortcuts_layout = QVBoxLayout(shortcuts_group)
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Action", "Shortcut", "Category"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        rows = self._keybinds.resolved_keybinds()
        table.setRowCount(len(rows))
        for row_index, entry in enumerate(rows):
            table.setItem(row_index, 0, QTableWidgetItem(entry.label))
            table.setItem(row_index, 1, QTableWidgetItem(entry.sequence or "-"))
            table.setItem(row_index, 2, QTableWidgetItem(entry.category))
        shortcuts_layout.addWidget(table)
        layout.addWidget(shortcuts_group, 1)

        selection_group = QGroupBox("Track Selection Behavior")
        selection_layout = QVBoxLayout(selection_group)
        for left, right in selection_behavior_rows(self._album_artwork_selection_mode):
            line = QLabel(f"{left}: {right}")
            line.setObjectName("StatusDetail")
            selection_layout.addWidget(line)
        layout.addWidget(selection_group)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)
