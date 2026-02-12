"""Cross-card track selection state manager."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal


class SelectionManager(QObject):
    """Manages selected track paths across multiple AlbumCards."""

    selection_changed = Signal(list)  # list[Path]
    track_toggled = Signal(Path, bool)  # (path, is_selected)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._selected: set[Path] = set()

    def toggle(self, path: Path) -> None:
        if path in self._selected:
            self._selected.discard(path)
            self.track_toggled.emit(path, False)
        else:
            self._selected.add(path)
            self.track_toggled.emit(path, True)
        self.selection_changed.emit(list(self._selected))

    def select(self, path: Path) -> None:
        if path not in self._selected:
            self._selected.add(path)
            self.track_toggled.emit(path, True)
            self.selection_changed.emit(list(self._selected))

    def deselect(self, path: Path) -> None:
        if path in self._selected:
            self._selected.discard(path)
            self.track_toggled.emit(path, False)
            self.selection_changed.emit(list(self._selected))

    def is_selected(self, path: Path) -> bool:
        return path in self._selected

    def clear(self) -> None:
        cleared = list(self._selected)
        self._selected.clear()
        for path in cleared:
            self.track_toggled.emit(path, False)
        self.selection_changed.emit([])

    def selected_paths(self) -> list[Path]:
        return list(self._selected)

    def select_all(self, paths: list[Path]) -> None:
        changed = False
        for p in paths:
            if p not in self._selected:
                self._selected.add(p)
                self.track_toggled.emit(p, True)
                changed = True
        if changed:
            self.selection_changed.emit(list(self._selected))
