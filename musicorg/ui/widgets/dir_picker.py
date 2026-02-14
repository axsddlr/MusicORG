"""Directory picker widget: line edit + browse button."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget


class DirPicker(QWidget):
    """A widget combining a line edit and browse button for directory selection."""

    path_changed = Signal(str)

    def __init__(self, label: str = "Browse...", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._line_edit = QLineEdit()
        self._line_edit.setPlaceholderText("Select a directory...")
        self._browse_btn = QPushButton(label)
        self._browse_btn.setMinimumWidth(92)
        self._browse_btn.setMaximumWidth(132)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._line_edit, 1)
        layout.addWidget(self._browse_btn)

        self._browse_btn.clicked.connect(self._browse)
        self._line_edit.textChanged.connect(self.path_changed.emit)

    def path(self) -> str:
        return self._line_edit.text().strip()

    def set_path(self, path: str) -> None:
        self._line_edit.setText(path)

    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Select Directory", self._line_edit.text()
        )
        if directory:
            self._line_edit.setText(directory)
