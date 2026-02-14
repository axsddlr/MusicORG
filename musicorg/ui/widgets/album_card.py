"""AlbumCard and TrackRow widgets for the album browser."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from musicorg.ui.models.file_table_model import FileTableRow
from musicorg.ui.widgets.selection_manager import SelectionManager


def _format_duration(seconds: float) -> str:
    """Format seconds as m:ss."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"


def _format_total_duration(seconds: float) -> str:
    """Format total duration as Xh Ym or Xm Ys."""
    total = int(seconds)
    if total >= 3600:
        h = total // 3600
        m = (total % 3600) // 60
        return f"{h}h {m}m"
    m = total // 60
    s = total % 60
    return f"{m}m {s}s"


class TrackRow(QFrame):
    """Clickable row: track # | title | duration. Toggles selection."""

    def __init__(
        self,
        row: FileTableRow,
        selection_manager: SelectionManager,
        on_context_action=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TrackRow")
        self._path: Path = row.path
        self._title_text = row.tags.title or row.filename
        self._selection_manager: SelectionManager | None = selection_manager
        self._on_context_action = on_context_action
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setProperty("focused", "false")
        self.setAccessibleName(f"Track {self._title_text}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)

        # Track number
        track_num = QLabel(str(row.tags.track) if row.tags.track else "-")
        track_num.setObjectName("TrackNumber")
        track_num.setFixedWidth(24)
        track_num.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(track_num)

        # Title
        title = QLabel(self._title_text)
        title.setObjectName("TrackTitle")
        layout.addWidget(title, 1)

        # Duration
        dur_text = _format_duration(row.tags.duration) if row.tags.duration > 0 else ""
        dur_label = QLabel(dur_text)
        dur_label.setObjectName("TrackDuration")
        dur_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(dur_label)

        # Initial selected state
        self._update_selected(selection_manager.is_selected(self._path))

        # Listen for toggle changes
        selection_manager.track_toggled.connect(self._on_track_toggled)

    def _on_track_toggled(self, path: Path, selected: bool) -> None:
        if path == self._path:
            self._update_selected(selected)

    def _update_selected(self, selected: bool) -> None:
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.addAction("Tag Editor", lambda: self._fire_context("editor"))
        menu.addAction("Auto-Tag", lambda: self._fire_context("autotag"))
        menu.addAction("Artwork Downloader", lambda: self._fire_context("artwork"))
        menu.exec(event.globalPos())
        event.accept()

    def _fire_context(self, action: str) -> None:
        if self._on_context_action is not None:
            self._on_context_action(action, [self._path])

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._selection_manager is not None:
            self._selection_manager.toggle(self._path)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self._selection_manager is not None:
                self._selection_manager.toggle(self._path)
                event.accept()
                return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        self.setProperty("focused", "true")
        self.style().unpolish(self)
        self.style().polish(self)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.setProperty("focused", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        super().focusOutEvent(event)

    def cleanup(self) -> None:
        if self._selection_manager is None:
            return
        try:
            self._selection_manager.track_toggled.disconnect(self._on_track_toggled)
        except (RuntimeError, TypeError):
            pass
        self._selection_manager = None

    def deleteLater(self) -> None:
        self.cleanup()
        super().deleteLater()


class AlbumCard(QFrame):
    """Album card: cover art left | metadata + two-column track grid right."""

    album_clicked = Signal(bytes)
    send_to_editor = Signal(list)
    send_to_autotag = Signal(list)
    send_to_artwork = Signal(list)

    def __init__(
        self,
        album_name: str,
        rows: list[FileTableRow],
        selection_manager: SelectionManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AlbumCard")
        self._track_rows: list[TrackRow] = []
        self._all_paths: list[Path] = [r.path for r in rows]
        self._path_set: set[Path] = set(self._all_paths)
        self._selection_manager: SelectionManager | None = selection_manager
        self._selection_badge = QLabel("")
        self._selection_badge.setObjectName("AlbumSelectedBadge")
        self._selection_badge.setVisible(False)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(14)

        # Cover art (120x120)
        cover_label = QLabel()
        cover_label.setObjectName("AlbumCover")
        cover_label.setMinimumSize(108, 108)
        cover_label.setMaximumSize(132, 132)
        cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        artwork = self._find_artwork(rows)
        self._artwork_data: bytes = artwork
        if artwork:
            pixmap = QPixmap()
            if pixmap.loadFromData(artwork):
                scaled = pixmap.scaled(
                    120, 120,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                cover_label.setPixmap(scaled)
            else:
                cover_label.setText("No Art")
        else:
            cover_label.setText("No Art")
        main_layout.addWidget(cover_label, 0, Qt.AlignmentFlag.AlignTop)

        # Right side: metadata + tracks
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(4)

        # Album header
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        title_label = QLabel(album_name)
        title_label.setObjectName("AlbumTitle")
        header_layout.addWidget(title_label)

        year = self._find_year(rows)
        if year:
            year_label = QLabel(str(year))
            year_label.setObjectName("AlbumYear")
            header_layout.addWidget(year_label)
        header_layout.addWidget(self._selection_badge)
        header_layout.addStretch()
        self._add_album_action_button(header_layout, "Tag", "editor")
        self._add_album_action_button(header_layout, "Auto", "autotag")
        self._add_album_action_button(header_layout, "Art", "artwork")
        right.addLayout(header_layout)

        # Meta: track count + total duration
        total_duration = sum(r.tags.duration for r in rows)
        track_count = len(rows)
        meta_parts = [f"{track_count} track{'s' if track_count != 1 else ''}"]
        if total_duration > 0:
            meta_parts.append(_format_total_duration(total_duration))
        meta_label = QLabel(" \u2022 ".join(meta_parts))
        meta_label.setObjectName("AlbumMeta")
        right.addWidget(meta_label)

        # Build track grid with disc grouping
        discs = self._group_by_disc(rows)
        show_disc_headers = len(discs) > 1

        for disc_num in sorted(discs):
            disc_rows = discs[disc_num]
            if show_disc_headers:
                disc_header = QLabel(f"Disc {disc_num}")
                disc_header.setObjectName("DiscHeader")
                right.addWidget(disc_header)

            # Two-column grid
            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(0)
            half = math.ceil(len(disc_rows) / 2)
            for i, row in enumerate(disc_rows):
                track_widget = TrackRow(row, selection_manager, self._on_context_action)
                self._track_rows.append(track_widget)
                if i < half:
                    grid.addWidget(track_widget, i, 0)
                else:
                    grid.addWidget(track_widget, i - half, 1)
            right.addLayout(grid)

        right.addStretch()
        main_layout.addLayout(right, 1)
        selection_manager.selection_changed.connect(self._on_selection_changed)
        self._on_selection_changed(selection_manager.selected_paths())

    def _on_context_action(self, action: str, paths: list[Path]) -> None:
        if action == "editor":
            self.send_to_editor.emit(paths)
        elif action == "autotag":
            self.send_to_autotag.emit(paths)
        elif action == "artwork":
            self.send_to_artwork.emit(paths)

    def _add_album_action_button(
        self,
        layout: QHBoxLayout,
        label: str,
        action: str,
    ) -> None:
        button = QPushButton(label)
        button.setObjectName("AlbumActionButton")
        button.setProperty("compact", "true")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(
            lambda _checked=False, selected_action=action: self._on_context_action(
                selected_action,
                self._all_paths,
            )
        )
        layout.addWidget(button)

    def _on_selection_changed(self, selected_paths: list[Path]) -> None:
        selected_count = sum(1 for path in selected_paths if path in self._path_set)
        if selected_count > 0:
            self._selection_badge.setText(f"{selected_count} selected")
            self._selection_badge.setVisible(True)
        else:
            self._selection_badge.clear()
            self._selection_badge.setVisible(False)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.addAction("Tag Editor", lambda: self.send_to_editor.emit(self._all_paths))
        menu.addAction("Auto-Tag", lambda: self.send_to_autotag.emit(self._all_paths))
        menu.addAction(
            "Artwork Downloader",
            lambda: self.send_to_artwork.emit(self._all_paths),
        )
        menu.exec(event.globalPos())
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._artwork_data:
            self.album_clicked.emit(self._artwork_data)
        super().mousePressEvent(event)

    def cleanup(self) -> None:
        if self._selection_manager is not None:
            try:
                self._selection_manager.selection_changed.disconnect(self._on_selection_changed)
            except (RuntimeError, TypeError):
                pass
        self._selection_manager = None
        for track_row in self._track_rows:
            track_row.cleanup()
        self._track_rows.clear()

    @staticmethod
    def _find_artwork(rows: list[FileTableRow]) -> bytes:
        for row in rows:
            if row.tags.artwork_data:
                return row.tags.artwork_data
        return b""

    @staticmethod
    def _find_year(rows: list[FileTableRow]) -> int:
        for row in rows:
            if row.tags.year:
                return row.tags.year
        return 0

    @staticmethod
    def _group_by_disc(rows: list[FileTableRow]) -> dict[int, list[FileTableRow]]:
        discs: dict[int, list[FileTableRow]] = {}
        for row in rows:
            disc = row.tags.disc if row.tags.disc > 0 else 1
            discs.setdefault(disc, []).append(row)
        return discs
