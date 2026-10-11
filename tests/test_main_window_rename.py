"""Template rename must run through RawFilesPanel's managed rename worker."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from musicorg.ui import main_window
from musicorg.ui.main_window import MainWindow


def _fake_window(paths: list[Path]) -> SimpleNamespace:
    return SimpleNamespace(
        _selected_paths_for_tools=lambda: paths,
        _active_selection_panel_label=lambda: "Source",
        _status_strip=MagicMock(),
        _raw_files_panel=MagicMock(),
    )


def _patch_dialog(monkeypatch: pytest.MonkeyPatch, accepted: bool, items: list) -> None:
    dialog = MagicMock()
    dialog.exec.return_value = accepted
    dialog.rename_items.return_value = items
    monkeypatch.setattr(main_window, "TemplateRenameDialog", lambda *a, **k: dialog)


def test_template_rename_delegates_to_raw_files_panel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    items = [(tmp_path / "a.mp3", tmp_path / "01 Song.mp3")]
    _patch_dialog(monkeypatch, True, items)
    window = _fake_window([tmp_path / "a.mp3"])

    MainWindow._open_template_rename_from_selection(window)

    window._raw_files_panel._start_batch_rename.assert_called_once_with(items)


def test_template_rename_cancelled_dialog_starts_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_dialog(monkeypatch, False, [(tmp_path / "a.mp3", tmp_path / "b.mp3")])
    window = _fake_window([tmp_path / "a.mp3"])

    MainWindow._open_template_rename_from_selection(window)

    window._raw_files_panel._start_batch_rename.assert_not_called()


def test_template_rename_without_selection_shows_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_dialog(monkeypatch, True, [])
    window = _fake_window([])

    MainWindow._open_template_rename_from_selection(window)

    window._raw_files_panel._start_batch_rename.assert_not_called()
    window._status_strip.show_message.assert_called_once()
