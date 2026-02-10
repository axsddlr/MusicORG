"""QAbstractTableModel for match candidates."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from musicorg.core.autotagger import MatchCandidate

COLUMNS = ["Source", "Artist", "Album", "Year", "Match %"]


class MatchModel(QAbstractTableModel):
    """Table model for displaying auto-tag match candidates."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._candidates: list[MatchCandidate] = []

    def set_candidates(self, candidates: list[MatchCandidate]) -> None:
        self.beginResetModel()
        self._candidates = candidates
        self.endResetModel()

    def clear(self) -> None:
        self.beginResetModel()
        self._candidates = []
        self.endResetModel()

    def get_candidate(self, index: int) -> MatchCandidate | None:
        if 0 <= index < len(self._candidates):
            return self._candidates[index]
        return None

    # -- QAbstractTableModel overrides --

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._candidates)

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

        c = self._candidates[index.row()]
        col = index.column()

        if col == 0:
            return c.source
        elif col == 1:
            return c.artist
        elif col == 2:
            return c.album
        elif col == 3:
            return str(c.year) if c.year else ""
        elif col == 4:
            return f"{c.match_percent:.1f}%"
        return None
