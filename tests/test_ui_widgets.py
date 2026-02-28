"""Tests for musicorg.ui widgets."""

import pytest
from PySide6.QtWidgets import QApplication

from musicorg.ui.keybindings import (
    KeybindRegistry,
    KeybindSpec,
    KeybindConflictError,
    normalize_album_artwork_selection_mode,
    selection_behavior_rows,
    selection_behavior_hint,
    DEFAULT_KEYBINDS,
)
from musicorg.ui.widgets.selection_manager import SelectionManager


class TestKeybindRegistry:
    """Tests for KeybindRegistry."""

    def test_registry_creation(self):
        """Test KeybindRegistry can be created."""
        registry = KeybindRegistry(DEFAULT_KEYBINDS)
        assert registry is not None

    def test_registry_with_overrides(self):
        """Test KeybindRegistry accepts overrides."""
        overrides = {"app.exit": "Ctrl+W"}
        registry = KeybindRegistry(DEFAULT_KEYBINDS, overrides=overrides)
        assert registry.sequence_for("app.exit") == "Ctrl+W"

    def test_registry_sequence_for(self):
        """Test sequence_for returns correct sequence."""
        registry = KeybindRegistry(DEFAULT_KEYBINDS)
        sequence = registry.sequence_for("app.exit")
        assert sequence == "Ctrl+Q"

    def test_registry_sequence_for_unknown_id(self):
        """Test sequence_for raises KeyError for unknown id."""
        registry = KeybindRegistry(DEFAULT_KEYBINDS)
        with pytest.raises(KeyError):
            registry.sequence_for("unknown.id")

    def test_registry_resolved_keybinds(self):
        """Test resolved_keybinds returns list."""
        registry = KeybindRegistry(DEFAULT_KEYBINDS)
        keybinds = registry.resolved_keybinds()
        assert isinstance(keybinds, list)
        assert len(keybinds) > 0

    def test_registry_detects_conflicts(self):
        """Test KeybindRegistry detects duplicate sequences."""
        specs = (
            KeybindSpec(
                id="test.one",
                label="One",
                default_sequence="Ctrl+A",
                description="Test one",
                category="Test",
            ),
            KeybindSpec(
                id="test.two",
                label="Two",
                default_sequence="Ctrl+A",
                description="Test two",
                category="Test",
            ),
        )
        with pytest.raises(KeybindConflictError):
            KeybindRegistry(specs)

    def test_registry_no_conflict_different_scopes(self):
        """Test no conflict for same sequence in different scopes."""
        specs = (
            KeybindSpec(
                id="test.one",
                label="One",
                default_sequence="Ctrl+A",
                description="Test one",
                category="Test",
                scope="window",
            ),
            KeybindSpec(
                id="test.two",
                label="Two",
                default_sequence="Ctrl+A",
                description="Test two",
                category="Test",
                scope="editor",
            ),
        )
        # Should not raise
        registry = KeybindRegistry(specs)
        assert registry is not None


class TestAlbumArtworkSelectionMode:
    """Tests for album artwork selection mode helpers."""

    def test_normalize_album_artwork_selection_mode_valid(self):
        """Test normalize accepts valid modes."""
        assert normalize_album_artwork_selection_mode("none") == "none"
        assert normalize_album_artwork_selection_mode("single_click") == "single_click"
        assert normalize_album_artwork_selection_mode("double_click") == "double_click"

    def test_normalize_album_artwork_selection_mode_invalid(self):
        """Test normalize returns default for invalid modes."""
        assert normalize_album_artwork_selection_mode("invalid") == "single_click"
        assert normalize_album_artwork_selection_mode(None) == "single_click"
        assert normalize_album_artwork_selection_mode(123) == "single_click"

    def test_normalize_album_artwork_selection_mode_case_insensitive(self):
        """Test normalize is case insensitive."""
        assert normalize_album_artwork_selection_mode("SINGLE_CLICK") == "single_click"
        assert normalize_album_artwork_selection_mode("Single_Click") == "single_click"

    def test_selection_behavior_rows_single_click(self):
        """Test selection_behavior_rows for single_click mode."""
        rows = selection_behavior_rows("single_click")
        assert isinstance(rows, tuple)
        assert len(rows) > 5

    def test_selection_behavior_rows_double_click(self):
        """Test selection_behavior_rows for double_click mode."""
        rows = selection_behavior_rows("double_click")
        assert isinstance(rows, tuple)
        assert len(rows) > 5

    def test_selection_behavior_rows_none(self):
        """Test selection_behavior_rows for none mode."""
        rows = selection_behavior_rows("none")
        assert isinstance(rows, tuple)
        assert any("Off" in row for row in rows)

    def test_selection_behavior_hint(self):
        """Test selection_behavior_hint returns string."""
        hint = selection_behavior_hint("single_click")
        assert isinstance(hint, str)
        assert "Ctrl+Click" in hint or "Shift+Click" in hint


class TestSelectionManager:
    """Tests for SelectionManager."""

    def test_selection_manager_basic_operations(self):
        """Test SelectionManager basic select/clear/toggle operations."""
        from PySide6.QtWidgets import QWidget
        from pathlib import Path
        
        parent = QWidget()
        manager = SelectionManager(parent)
        
        # Test initial state
        assert manager.selected_paths() == []
        
        # Test select
        paths = [Path("/test/file1.mp3"), Path("/test/file2.mp3")]
        manager.select(paths)
        selected = manager.selected_paths()
        assert len(selected) == 2
        
        # Test clear
        manager.clear()
        assert manager.selected_paths() == []
        
        # Test toggle
        path = Path("/test/file1.mp3")
        manager.toggle(path)
        assert path in manager.selected_paths()
        manager.toggle(path)
        assert path not in manager.selected_paths()

    def test_selection_manager_set_ordered_paths(self):
        """Test set_ordered_paths stores the order."""
        from PySide6.QtWidgets import QWidget
        from pathlib import Path
        
        parent = QWidget()
        manager = SelectionManager(parent)
        
        paths = [Path("/test/file1.mp3"), Path("/test/file2.mp3")]
        manager.set_ordered_paths(paths)
        assert len(manager.selected_paths()) == 0  # Not selected yet

    def test_selection_manager_select_all(self):
        """Test select_all selects all ordered paths."""
        from PySide6.QtWidgets import QWidget
        from pathlib import Path
        
        parent = QWidget()
        manager = SelectionManager(parent)
        
        paths = [Path("/test/file1.mp3"), Path("/test/file2.mp3"), Path("/test/file3.mp3")]
        manager.set_ordered_paths(paths)
        manager.select_all(paths)
        selected = manager.selected_paths()
        assert len(selected) == 3
