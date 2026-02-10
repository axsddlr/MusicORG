"""QTableView configured for audio file listings."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QWidget

from musicorg.ui.models.file_table_model import FileTableModel


class FileTable(QTableView):
    """Table view for displaying audio files."""

    selection_changed = Signal(list)  # list[int] of selected row indices

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = FileTableModel(self)
        self.setModel(self._model)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.verticalHeader().setVisible(False)

        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 6):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

    @property
    def file_model(self) -> FileTableModel:
        return self._model

    def selected_indices(self) -> list[int]:
        return sorted({idx.row() for idx in self.selectionModel().selectedRows()})

    def selectionChanged(self, selected, deselected) -> None:
        super().selectionChanged(selected, deselected)
        self.selection_changed.emit(self.selected_indices())
