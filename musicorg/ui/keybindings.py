"""Central keybinding registry and action helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Mapping

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True, slots=True)
class KeybindSpec:
    """Declarative keybinding specification.

    Template for future keybinds:
    1. Add a new KeybindSpec to DEFAULT_KEYBINDS.
    2. Bind that id to an action handler in MainWindow.
    3. It appears automatically in the Keyboard Shortcuts dialog.
    """

    id: str
    label: str
    default_sequence: str
    description: str
    category: str
    scope: str = "window"


@dataclass(frozen=True, slots=True)
class ResolvedKeybind:
    """A keybinding resolved with overrides and normalized sequence."""

    id: str
    label: str
    sequence: str
    description: str
    category: str
    scope: str


class KeybindConflictError(ValueError):
    """Raised when two keybinds share the same shortcut in the same scope."""


AlbumArtworkSelectionMode = Literal["none", "single_click", "double_click"]
DEFAULT_ALBUM_ARTWORK_SELECTION_MODE: AlbumArtworkSelectionMode = "single_click"


DEFAULT_KEYBINDS: tuple[KeybindSpec, ...] = (
    KeybindSpec(
        id="app.exit",
        label="Exit Application",
        default_sequence="Ctrl+Q",
        description="Close MusicOrg.",
        category="Application",
    ),
    KeybindSpec(
        id="app.preferences",
        label="Open Preferences",
        default_sequence="Ctrl+,",
        description="Open application settings.",
        category="Application",
    ),
    KeybindSpec(
        id="app.select_all",
        label="Select All Tracks",
        default_sequence="Ctrl+A",
        description="Select all tracks in the current view.",
        category="Application",
    ),
    KeybindSpec(
        id="tools.open_tag_editor",
        label="Open Tag Editor",
        default_sequence="Ctrl+E",
        description="Open Tag Editor for selected files.",
        category="Tools",
    ),
    KeybindSpec(
        id="tools.open_autotag",
        label="Open Auto-Tag",
        default_sequence="Ctrl+T",
        description="Open Auto-Tag for selected files.",
        category="Tools",
    ),
    KeybindSpec(
        id="tools.open_artwork",
        label="Open Artwork Downloader",
        default_sequence="Ctrl+Shift+A",
        description="Open Artwork Downloader for selected files.",
        category="Tools",
    ),
    KeybindSpec(
        id="help.keyboard_shortcuts",
        label="Show Keyboard Shortcuts",
        default_sequence="Ctrl+/",
        description="Show keyboard shortcut and selection behavior reference.",
        category="Help",
    ),
)


_BASE_SELECTION_BEHAVIOR_ROWS: tuple[tuple[str, str], ...] = (
    ("Left Click", "No selection change"),
    ("Ctrl + Left Click", "Toggle one track"),
    ("Shift + Left Click", "Select range from anchor"),
    ("Shift + Left Click (Selected Track)", "Deselect clicked track"),
    ("Ctrl + Shift + Left Click", "Add range to current selection"),
)


def normalize_album_artwork_selection_mode(
    value: object,
) -> AlbumArtworkSelectionMode:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"none", "single_click", "double_click"}:
            return lowered
    return DEFAULT_ALBUM_ARTWORK_SELECTION_MODE


def selection_behavior_rows(
    mode: AlbumArtworkSelectionMode,
) -> tuple[tuple[str, str], ...]:
    rows = list(_BASE_SELECTION_BEHAVIOR_ROWS)
    if mode == "single_click":
        rows.extend(
            [
                ("Click Album Artwork", "Toggle full album selection"),
                ("Ctrl + Click Album Artwork", "Add/remove album in selection"),
            ]
        )
    elif mode == "double_click":
        rows.extend(
            [
                ("Double Click Album Artwork", "Toggle full album selection"),
                ("Ctrl + Double Click Album Artwork", "Add/remove album in selection"),
            ]
        )
    else:
        rows.append(("Album Artwork Selection", "Off"))
    return tuple(rows)


def selection_behavior_hint(mode: AlbumArtworkSelectionMode) -> str:
    base = "Selection: Ctrl+Click toggle | Shift+Click range/deselect"
    if mode == "single_click":
        return f"{base} | Click artwork toggle album"
    if mode == "double_click":
        return f"{base} | Double-click artwork toggle album"
    return base


class KeybindRegistry:
    """Resolve keybind specs with overrides and validate conflicts."""

    def __init__(
        self,
        specs: tuple[KeybindSpec, ...],
        overrides: Mapping[str, str] | None = None,
    ) -> None:
        self._specs = specs
        self._specs_by_id = self._build_spec_index(specs)
        self._sequences: dict[str, str] = {}
        data = dict(overrides or {})
        for spec in specs:
            raw_sequence = data.get(spec.id, spec.default_sequence)
            self._sequences[spec.id] = self._normalize_sequence(raw_sequence, spec.id)
        self._validate_conflicts()

    @staticmethod
    def _build_spec_index(specs: tuple[KeybindSpec, ...]) -> dict[str, KeybindSpec]:
        index: dict[str, KeybindSpec] = {}
        for spec in specs:
            if spec.id in index:
                raise ValueError(f"Duplicate keybind id: {spec.id}")
            index[spec.id] = spec
        return index

    @staticmethod
    def _normalize_sequence(raw: str, keybind_id: str) -> str:
        if not isinstance(raw, str):
            raise ValueError(f"Shortcut override for {keybind_id} must be a string")
        text = raw.strip()
        if not text:
            return ""
        sequence = QKeySequence.fromString(text, QKeySequence.SequenceFormat.PortableText)
        if sequence.isEmpty():
            raise ValueError(f"Invalid shortcut sequence for {keybind_id}: {raw}")
        return sequence.toString(QKeySequence.SequenceFormat.PortableText)

    def _validate_conflicts(self) -> None:
        occupied: dict[tuple[str, str], str] = {}
        for spec in self._specs:
            sequence = self._sequences.get(spec.id, "")
            if not sequence:
                continue
            key = (spec.scope, sequence)
            existing = occupied.get(key)
            if existing is not None and existing != spec.id:
                raise KeybindConflictError(
                    f"Shortcut conflict: {sequence} used by {existing} and {spec.id}"
                )
            occupied[key] = spec.id

    def sequence_for(self, keybind_id: str) -> str:
        if keybind_id not in self._specs_by_id:
            raise KeyError(f"Unknown keybind id: {keybind_id}")
        return self._sequences[keybind_id]

    def resolved_keybinds(self) -> list[ResolvedKeybind]:
        rows = [
            ResolvedKeybind(
                id=spec.id,
                label=spec.label,
                sequence=self._sequences[spec.id],
                description=spec.description,
                category=spec.category,
                scope=spec.scope,
            )
            for spec in self._specs
        ]
        return sorted(rows, key=lambda row: (row.category, row.label))


def create_bound_action(
    *,
    parent: QWidget,
    text: str,
    keybind_id: str,
    registry: KeybindRegistry,
    handler: Callable[[], None],
) -> QAction:
    """Create a QAction wired to a handler and shortcut from the registry."""

    action = QAction(text, parent)
    shortcut = registry.sequence_for(keybind_id)
    if shortcut:
        action.setShortcut(shortcut)
        action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
    action.triggered.connect(handler)
    return action
