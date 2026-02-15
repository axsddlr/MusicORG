"""Tests for keybinding registry behavior."""

import pytest

from musicorg.ui.keybindings import (
    selection_behavior_hint,
    selection_behavior_rows,
    normalize_album_artwork_selection_mode,
    KeybindConflictError,
    KeybindRegistry,
    KeybindSpec,
)


def _specs() -> tuple[KeybindSpec, ...]:
    return (
        KeybindSpec(
            id="a.one",
            label="Action One",
            default_sequence="Ctrl+1",
            description="First action",
            category="Test",
        ),
        KeybindSpec(
            id="a.two",
            label="Action Two",
            default_sequence="Ctrl+2",
            description="Second action",
            category="Test",
        ),
    )


def test_registry_uses_defaults_when_no_overrides() -> None:
    registry = KeybindRegistry(_specs())
    assert registry.sequence_for("a.one") == "Ctrl+1"
    assert registry.sequence_for("a.two") == "Ctrl+2"


def test_registry_applies_override() -> None:
    registry = KeybindRegistry(_specs(), {"a.two": "Ctrl+Shift+2"})
    assert registry.sequence_for("a.two") == "Ctrl+Shift+2"


def test_registry_rejects_non_string_sequence_override() -> None:
    with pytest.raises(ValueError):
        KeybindRegistry(_specs(), {"a.one": 42})  # type: ignore[arg-type]


def test_registry_detects_conflict() -> None:
    with pytest.raises(KeybindConflictError):
        KeybindRegistry(_specs(), {"a.two": "Ctrl+1"})


def test_selection_behavior_rows_for_single_click_mode() -> None:
    rows = selection_behavior_rows("single_click")
    assert ("Click Album Artwork", "Toggle full album selection") in rows


def test_selection_behavior_hint_for_double_click_mode() -> None:
    hint = selection_behavior_hint("double_click")
    assert "Double-click artwork" in hint


def test_normalize_album_artwork_selection_mode_defaults_to_single_click() -> None:
    assert normalize_album_artwork_selection_mode("invalid") == "single_click"
