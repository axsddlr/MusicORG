"""Tests for SelectionManager interaction behavior."""

from pathlib import Path

from musicorg.ui.widgets.selection_manager import SelectionManager


def test_toggle_group_non_additive_selects_then_deselects() -> None:
    manager = SelectionManager()
    group = [Path("a.mp3"), Path("b.mp3"), Path("c.mp3")]

    manager.toggle_group(group, additive=False)
    assert manager.selected_paths() == group

    manager.toggle_group(group, additive=False)
    assert manager.selected_paths() == []


def test_toggle_group_additive_adds_and_removes_group_only() -> None:
    manager = SelectionManager()
    base = Path("base.mp3")
    group = [Path("a.mp3"), Path("b.mp3")]

    manager.select(base)
    manager.toggle_group(group, additive=True)
    selected = set(manager.selected_paths())
    assert selected == {base, *group}

    manager.toggle_group(group, additive=True)
    assert manager.selected_paths() == [base]


def test_select_group_replaces_when_not_additive() -> None:
    manager = SelectionManager()
    manager.select(Path("x.mp3"))
    group = [Path("a.mp3"), Path("b.mp3")]

    manager.select_group(group, additive=False)
    assert manager.selected_paths() == group


def test_shift_click_selected_track_deselects_it() -> None:
    manager = SelectionManager()
    a = Path("a.mp3")
    b = Path("b.mp3")
    manager.set_ordered_paths([a, b])

    manager.select_range_to(a)
    manager.select_range_to(b)
    assert manager.selected_paths() == [a, b]

    manager.select_range_to(a)
    assert manager.selected_paths() == [b]
