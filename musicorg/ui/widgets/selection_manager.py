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
        self._anchor: Path | None = None
        self._ordered_paths: list[Path] = []
        self._order_index: dict[Path, int] = {}

    def set_ordered_paths(self, paths: list[Path]) -> None:
        seen: set[Path] = set()
        ordered: list[Path] = []
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            ordered.append(path)
        self._ordered_paths = ordered
        self._order_index = {path: index for index, path in enumerate(ordered)}
        if self._anchor is not None and self._anchor not in self._order_index:
            self._anchor = None

    def set_anchor(self, path: Path) -> None:
        self._anchor = path

    def is_group_fully_selected(self, paths: list[Path]) -> bool:
        group = set(paths)
        return bool(group) and group.issubset(self._selected)

    def toggle(self, path: Path) -> None:
        if path in self._selected:
            self._selected.discard(path)
            self.track_toggled.emit(path, False)
        else:
            self._selected.add(path)
            self.track_toggled.emit(path, True)
        self._anchor = path
        self.selection_changed.emit(list(self._selected))

    def select(self, path: Path) -> None:
        if path not in self._selected:
            self._selected.add(path)
            self.track_toggled.emit(path, True)
            self.selection_changed.emit(list(self._selected))
        self._anchor = path

    def deselect(self, path: Path) -> None:
        if path in self._selected:
            self._selected.discard(path)
            self.track_toggled.emit(path, False)
            self.selection_changed.emit(list(self._selected))

    def is_selected(self, path: Path) -> bool:
        return path in self._selected

    def select_range_to(self, path: Path, *, additive: bool = False) -> None:
        if path not in self._order_index:
            if additive:
                self.select(path)
            else:
                self._replace_selection({path})
                self._anchor = path
            return
        if self._anchor is None or self._anchor not in self._order_index:
            if additive:
                self.select(path)
            else:
                self._replace_selection({path})
            self._anchor = path
            return

        start = self._order_index[self._anchor]
        end = self._order_index[path]
        if start > end:
            start, end = end, start
        range_selection = set(self._ordered_paths[start:end + 1])
        if additive:
            self._replace_selection(self._selected | range_selection)
        else:
            self._replace_selection(range_selection)

    def select_group(self, paths: list[Path], *, additive: bool = False) -> None:
        group = set(paths)
        if not group:
            return
        if additive:
            next_selection = self._selected | group
        else:
            next_selection = group
        self._replace_selection(next_selection)
        anchor = self._first_ordered_path(group)
        if anchor is not None:
            self._anchor = anchor

    def toggle_group(self, paths: list[Path], *, additive: bool = False) -> None:
        group = set(paths)
        if not group:
            return
        fully_selected = group.issubset(self._selected)
        if additive:
            if fully_selected:
                next_selection = self._selected - group
            else:
                next_selection = self._selected | group
        else:
            if fully_selected:
                next_selection = self._selected - group
            else:
                next_selection = group

        self._replace_selection(next_selection)
        if next_selection:
            anchor = self._first_ordered_path(group & next_selection)
            if anchor is None:
                anchor = self._first_ordered_path(next_selection)
            self._anchor = anchor
        else:
            self._anchor = None

    def clear(self) -> None:
        cleared = list(self._selected)
        self._selected.clear()
        self._anchor = None
        for path in cleared:
            self.track_toggled.emit(path, False)
        self.selection_changed.emit([])

    def selected_paths(self) -> list[Path]:
        if not self._selected:
            return []
        if self._ordered_paths:
            in_order = [path for path in self._ordered_paths if path in self._selected]
            extras = sorted(
                (path for path in self._selected if path not in self._order_index),
                key=lambda value: str(value),
            )
            return in_order + extras
        return sorted(self._selected, key=lambda value: str(value))

    def select_all(self, paths: list[Path]) -> None:
        self._replace_selection(self._selected | set(paths))

    def _replace_selection(self, new_selection: set[Path]) -> None:
        removed = self._selected - new_selection
        added = new_selection - self._selected
        if not removed and not added:
            return
        for path in removed:
            self.track_toggled.emit(path, False)
        for path in added:
            self.track_toggled.emit(path, True)
        self._selected = set(new_selection)
        self.selection_changed.emit(list(self._selected))

    def _first_ordered_path(self, paths: set[Path]) -> Path | None:
        if not paths:
            return None
        if self._ordered_paths:
            for ordered in self._ordered_paths:
                if ordered in paths:
                    return ordered
        return sorted(paths, key=lambda value: str(value))[0]
