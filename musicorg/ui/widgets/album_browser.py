"""Scrollable album card container."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from musicorg.ui.keybindings import (
    AlbumArtworkSelectionMode,
    DEFAULT_ALBUM_ARTWORK_SELECTION_MODE,
    normalize_album_artwork_selection_mode,
)
from musicorg.ui.models.file_table_model import FileTableRow
from musicorg.ui.widgets.album_card import AlbumCard
from musicorg.ui.widgets.selection_manager import SelectionManager

# Layout constants for album card height estimation
_CARD_COVER_AND_HEADER_HEIGHT = 80  # px for cover art + card header
_CARD_META_HEIGHT = 20  # px for metadata section
_CARD_TRACK_ROW_HEIGHT = 30  # px per track row in grid
_CARD_DISC_HEADER_HEIGHT = 20  # px per disc header separator
_MIN_SLOT_HEIGHT = 40  # minimum placeholder height
_MIN_BUFFER_HEIGHT = 120  # minimum buffer pixels for materialization


class AlbumBrowser(QScrollArea):
    """Scrollable container holding AlbumCard widgets.

    Only creates AlbumCard widgets for albums visible in the scroll viewport
    (plus a small buffer). Placeholders with estimated heights stand in for
    off-screen albums.
    """

    album_artwork_changed = Signal(bytes)
    send_to_editor = Signal(list)
    send_to_autotag = Signal(list)
    send_to_artwork = Signal(list)

    _MATERIALIZE_BUFFER_CARDS = 2
    _DEMATERIALIZE_BUFFER_CARDS = 5

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

        self._album_data: list[tuple[str, list[FileTableRow]]] = []
        self._selection_manager: SelectionManager | None = None
        self._slots: list[QWidget] = []
        self._materialized: set[int] = set()
        self._update_scheduled = False
        self._album_artwork_selection_mode: AlbumArtworkSelectionMode = (
            DEFAULT_ALBUM_ARTWORK_SELECTION_MODE
        )
        self._empty_label = QLabel("No albums found.\nScan a directory to begin.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("EmptyStateLabel")
        self._empty_label.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
        self._empty_label.setVisible(False)
        self._layout.addWidget(self._empty_label)

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def set_album_artwork_selection_mode(self, mode: AlbumArtworkSelectionMode) -> None:
        self._album_artwork_selection_mode = normalize_album_artwork_selection_mode(mode)
        for slot in self._slots:
            if isinstance(slot, AlbumCard):
                slot.set_album_artwork_selection_mode(self._album_artwork_selection_mode)

    def set_albums(
        self,
        albums: dict[str, list[FileTableRow]],
        selection_manager: SelectionManager,
    ) -> None:
        self.clear()
        self._selection_manager = selection_manager
        self._album_data = [(name, albums[name]) for name in sorted(albums)]
        ordered_paths = [row.path for _, rows in self._album_data for row in rows]
        selection_manager.set_ordered_paths(ordered_paths)

        if not self._album_data:
            self._empty_label.setText("No albums found.\nScan a directory to begin.")
            self._empty_label.setVisible(True)
            return

        for _album_name, rows in self._album_data:
            placeholder = self._make_placeholder(self._estimate_card_height(rows))
            self._slots.append(placeholder)
            self._layout.insertWidget(self._layout.count() - 1, placeholder)

        # Defer first visibility pass to after layout settles
        QTimer.singleShot(0, self._update_visible_cards)

    def scroll_to_top(self) -> None:
        self.verticalScrollBar().setValue(0)

    def clear(self) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                cleanup = getattr(widget, "cleanup", None)
                if callable(cleanup):
                    cleanup()
                widget.deleteLater()
        self._album_data = []
        self._selection_manager = None
        self._slots = []
        self._materialized.clear()
        self._update_scheduled = False
        self._empty_label.setVisible(True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule_update()

    def _on_scroll(self, _value: int) -> None:
        self._update_visible_cards()

    def _schedule_update(self) -> None:
        if not self._update_scheduled:
            self._update_scheduled = True
            QTimer.singleShot(0, self._do_scheduled_update)

    def _do_scheduled_update(self) -> None:
        self._update_scheduled = False
        self._update_visible_cards()

    def _update_visible_cards(self) -> None:
        if not self._slots:
            return

        # Hide empty label when there are albums
        self._empty_label.setVisible(False)

        viewport_top = self.verticalScrollBar().value()
        viewport_bottom = viewport_top + self.viewport().height()
        mat_buffer = self._buffer_pixels(self._MATERIALIZE_BUFFER_CARDS)
        demat_buffer = self._buffer_pixels(self._DEMATERIALIZE_BUFFER_CARDS)

        for index, widget in enumerate(self._slots):
            widget_top = widget.y()
            widget_height = max(widget.height(), widget.sizeHint().height(), 40)
            widget_bottom = widget_top + widget_height

            in_materialize_zone = (
                widget_bottom >= (viewport_top - mat_buffer)
                and widget_top <= (viewport_bottom + mat_buffer)
            )
            in_keep_zone = (
                widget_bottom >= (viewport_top - demat_buffer)
                and widget_top <= (viewport_bottom + demat_buffer)
            )

            if in_materialize_zone and index not in self._materialized:
                self._materialize_card(index)
            elif not in_keep_zone and index in self._materialized:
                self._dematerialize_card(index)

    def _materialize_card(self, index: int) -> None:
        if index in self._materialized:
            return
        if not (0 <= index < len(self._album_data)):
            return
        if self._selection_manager is None:
            return

        album_name, rows = self._album_data[index]
        card = AlbumCard(
            album_name,
            rows,
            self._selection_manager,
            album_artwork_selection_mode=self._album_artwork_selection_mode,
        )
        card.album_clicked.connect(self.album_artwork_changed.emit)
        card.send_to_editor.connect(self.send_to_editor.emit)
        card.send_to_autotag.connect(self.send_to_autotag.emit)
        card.send_to_artwork.connect(self.send_to_artwork.emit)

        self._replace_slot(index, card)
        self._materialized.add(index)

    def _dematerialize_card(self, index: int) -> None:
        if index not in self._materialized:
            return
        slot = self._slots[index]
        _album_name, rows = self._album_data[index]
        measured_height = max(
            slot.height(),
            slot.sizeHint().height(),
            self._estimate_card_height(rows),
        )
        placeholder = self._make_placeholder(measured_height)
        self._replace_slot(index, placeholder)
        self._materialized.discard(index)

    def _replace_slot(self, index: int, replacement: QWidget) -> None:
        current = self._slots[index]
        self._layout.replaceWidget(current, replacement)
        self._slots[index] = replacement
        cleanup = getattr(current, "cleanup", None)
        if callable(cleanup):
            cleanup()
        current.setParent(None)
        current.deleteLater()

    @staticmethod
    def _make_placeholder(height: int) -> QWidget:
        slot = QWidget()
        slot.setFixedHeight(max(_MIN_SLOT_HEIGHT, height))
        return slot

    @staticmethod
    def _estimate_card_height(rows: list[FileTableRow]) -> int:
        discs: dict[int, int] = {}
        for row in rows:
            disc = row.tags.disc if row.tags.disc > 0 else 1
            discs[disc] = discs.get(disc, 0) + 1
        grid_rows = sum(math.ceil(count / 2) for count in discs.values())
        disc_header_rows = max(0, len(discs) - 1)
        return int(
            _CARD_COVER_AND_HEADER_HEIGHT
            + _CARD_META_HEIGHT
            + (grid_rows * _CARD_TRACK_ROW_HEIGHT)
            + (disc_header_rows * _CARD_DISC_HEADER_HEIGHT)
        )

    def _buffer_pixels(self, cards: int) -> int:
        if not self._slots:
            return 0
        heights = [max(s.height(), s.sizeHint().height(), _MIN_SLOT_HEIGHT) for s in self._slots]
        avg = sum(heights) / len(heights)
        return int(max(_MIN_BUFFER_HEIGHT, avg * cards))
