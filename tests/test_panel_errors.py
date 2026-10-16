"""Panels must surface per-file failures from worker results."""

import pytest
from PySide6.QtWidgets import QMessageBox

from musicorg.ui.quicktag_panel import QuickTagPanel
from musicorg.ui.spotify_features_panel import SpotifyFeaturesPanel

CASES = [
    (QuickTagPanel, "_on_apply_finished"),
    (SpotifyFeaturesPanel, "_on_finished"),
]


@pytest.mark.parametrize("cls,handler", CASES)
def test_errors_reported(qtbot, monkeypatch, cls, handler):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a) or 0)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self) or 0)
    panel = cls()
    qtbot.addWidget(panel)
    emitted = []
    panel.tags_applied.connect(lambda: emitted.append(1))

    getattr(panel, handler)({"applied": 1, "total": 3, "errors": ["a.mp3: boom", "b.mp3: bad"]})

    text = panel._progress._label.text()
    assert "1" in text and "2 failed" in text
    assert shown, "failure details were not shown"
    assert emitted == [1]


@pytest.mark.parametrize("cls,handler", CASES)
def test_no_errors_no_dialog(qtbot, monkeypatch, cls, handler):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a) or 0)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self) or 0)
    panel = cls()
    qtbot.addWidget(panel)

    getattr(panel, handler)({"applied": 3, "total": 3, "errors": []})

    assert "failed" not in panel._progress._label.text()
    assert not shown
