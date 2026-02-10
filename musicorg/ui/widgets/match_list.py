"""Table widget for displaying match candidates."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QWidget

from musicorg.core.autotagger import MatchCandidate
from musicorg.ui.models.match_model import MatchModel


class MatchList(QTableView):
    """Table view for displaying auto-tag match candidates."""

    match_selected = Signal(int)  # row index of selected match

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = MatchModel(self)
        self.setModel(self._model)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)

        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        for i in range(5):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

        self.clicked.connect(lambda idx: self.match_selected.emit(idx.row()))

    @property
    def match_model(self) -> MatchModel:
        return self._model

    def selected_candidate(self) -> MatchCandidate | None:
        indices = self.selectionModel().selectedRows()
        if indices:
            return self._model.get_candidate(indices[0].row())
        return None
