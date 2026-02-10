"""QAbstractTableModel for audio file listings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from musicorg.core.tagger import TagData

COLUMNS = ["Filename", "Artist", "Album", "Track #", "Format", "Size"]


class FileTableRow:
    """Single row in the file table."""

    def __init__(self, path: Path, tags: TagData | None = None,
                 size: int = 0) -> None:
        self.path = path
        self.tags = tags or TagData()
        self.size = size

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def format(self) -> str:
        return self.path.suffix.upper().lstrip(".")

    @property
    def size_str(self) -> str:
        if self.size < 1024:
            return f"{self.size} B"
        elif self.size < 1024 * 1024:
            return f"{self.size / 1024:.1f} KB"
        else:
            return f"{self.size / (1024 * 1024):.1f} MB"


class FileTableModel(QAbstractTableModel):
    """Table model for displaying audio files with their tags."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[FileTableRow] = []

    def set_data(self, rows: list[FileTableRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def clear(self) -> None:
        self.beginResetModel()
        self._rows = []
        self.endResetModel()

    def get_row(self, index: int) -> FileTableRow | None:
        if 0 <= index < len(self._rows):
            return self._rows[index]
        return None

    def get_paths(self, indices: list[int]) -> list[Path]:
        return [self._rows[i].path for i in indices if 0 <= i < len(self._rows)]

    # -- QAbstractTableModel overrides --

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(COLUMNS):
                return COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None

        row = self._rows[index.row()]
        col = index.column()

        if col == 0:
            return row.filename
        elif col == 1:
            return row.tags.artist
        elif col == 2:
            return row.tags.album
        elif col == 3:
            return str(row.tags.track) if row.tags.track else ""
        elif col == 4:
            return row.format
        elif col == 5:
            return row.size_str
        return None
