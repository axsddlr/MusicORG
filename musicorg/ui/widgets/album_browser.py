"""Scrollable album card container."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from musicorg.ui.models.file_table_model import FileTableRow
from musicorg.ui.widgets.album_card import AlbumCard
from musicorg.ui.widgets.selection_manager import SelectionManager


class AlbumBrowser(QScrollArea):
    """Scrollable container holding AlbumCard widgets."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AlbumBrowser")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._inner = QWidget()
        self._inner.setObjectName("AlbumBrowserInner")
        self._layout = QVBoxLayout(self._inner)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(8)
        self._layout.addStretch()
        self.setWidget(self._inner)

    def set_albums(
        self,
        albums: dict[str, list[FileTableRow]],
        selection_manager: SelectionManager,
    ) -> None:
        self.clear()
        for album_name in sorted(albums):
            rows = albums[album_name]
            card = AlbumCard(album_name, rows, selection_manager)
            # Insert before the stretch
            self._layout.insertWidget(self._layout.count() - 1, card)

    def scroll_to_top(self) -> None:
        self.verticalScrollBar().setValue(0)

    def clear(self) -> None:
        # Remove all widgets except the trailing stretch
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                cleanup = getattr(widget, "cleanup", None)
                if callable(cleanup):
                    cleanup()
                widget.deleteLater()
