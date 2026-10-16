"""Overwrite-field semantics: None = all fields, [] = nothing; regex errors surface."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from musicorg.ui import autotag_panel
from musicorg.ui.autotag_panel import AutoTagPanel
from musicorg.workers import autotag_worker
from musicorg.workers.autotag_worker import ApplyMatchWorker, AutoTagWorker


def _run_apply(monkeypatch, **kw):
    tagger = MagicMock()
    monkeypatch.setattr(autotag_worker, "AutoTagger", lambda **k: tagger)
    ApplyMatchWorker(["a.mp3"], MagicMock(), **kw).run()
    return tagger


def test_all_fields_fill_empty_uses_overrides(qtbot, monkeypatch):
    tagger = _run_apply(monkeypatch, overwrite_fields=None, fill_empty_only=True)
    tagger.apply_match.assert_not_called()
    kwargs = tagger.apply_match_with_overrides.call_args.kwargs
    assert kwargs["fill_empty_only"] is True
    assert set(kwargs["overwrite_fields"]) >= {"title", "artist", "album", "artwork"}


def test_all_fields_not_fill_empty_uses_plain_apply(qtbot, monkeypatch):
    tagger = _run_apply(monkeypatch, overwrite_fields=None, fill_empty_only=False)
    tagger.apply_match.assert_called_once()
    tagger.apply_match_with_overrides.assert_not_called()


def test_empty_list_writes_nothing_via_overrides(qtbot, monkeypatch):
    tagger = _run_apply(monkeypatch, overwrite_fields=[], fill_empty_only=False)
    tagger.apply_match.assert_not_called()
    assert tagger.apply_match_with_overrides.call_args.kwargs["overwrite_fields"] == []


def _checkbox(on):
    return SimpleNamespace(isChecked=lambda: on)


def _fake_panel(*, all_on, fields_on, pattern="", fill=True):
    names = ["title", "artist", "album", "albumartist", "track", "disc", "year", "genre", "artwork"]
    p = SimpleNamespace(
        _overwrite_all=_checkbox(all_on),
        _fill_empty=_checkbox(fill),
        _files=["a.mp3"],
        _cache_db_path="",
        _discogs_token="",
        _apply_btn=MagicMock(),
        _progress=MagicMock(),
        _match_list=SimpleNamespace(selected_candidate=lambda: object()),
        _cleanup_pattern_edit=SimpleNamespace(text=lambda: pattern),
        _cleanup_replace_edit=SimpleNamespace(text=lambda: ""),
        _search_in_progress=False,
    )
    for n in names:
        setattr(p, f"_overwrite_{n}", _checkbox(fields_on))
    p._get_overwrite_fields = lambda: AutoTagPanel._get_overwrite_fields(p)
    return p


def test_panel_all_fields_is_none():
    assert AutoTagPanel._get_overwrite_fields(_fake_panel(all_on=True, fields_on=False)) is None


def test_panel_no_fields_refuses_to_start(monkeypatch):
    worker_cls = MagicMock()
    monkeypatch.setattr(autotag_panel, "ApplyMatchWorker", worker_cls)
    p = _fake_panel(all_on=False, fields_on=False)
    AutoTagPanel._apply_match(p)
    worker_cls.assert_not_called()
    assert "at least one field" in p._progress.finish.call_args.args[0]


def test_panel_invalid_regex_refuses_search(monkeypatch):
    worker_cls = MagicMock()
    warn = MagicMock()
    monkeypatch.setattr(autotag_panel, "AutoTagWorker", worker_cls)
    monkeypatch.setattr(autotag_panel.QMessageBox, "warning", warn)
    p = _fake_panel(all_on=True, fields_on=True, pattern="(")
    p._artist_edit = p._album_edit = p._title_edit = SimpleNamespace(text=lambda: "x")
    AutoTagPanel._do_search(p, "album")
    worker_cls.assert_not_called()
    assert "Invalid cleanup regex" in warn.call_args.args[2]


def test_worker_reports_invalid_regex(qtbot, monkeypatch):
    tagger = MagicMock()
    tagger.search_album_with_diagnostics.return_value = {"candidates": []}
    monkeypatch.setattr(autotag_worker, "AutoTagger", lambda **k: tagger)
    w = AutoTagWorker(["a.mp3"], regex_cleanup_pattern="(")
    msgs = []
    w.progress.connect(lambda c, t, m: msgs.append(m))
    w.run()
    assert any("Invalid cleanup regex" in m for m in msgs)
    tagger.search_album_with_diagnostics.assert_called_once()


@pytest.mark.parametrize("mode", ["album", "single"])
def test_worker_passes_cleaned_hints(qtbot, monkeypatch, mode):
    tagger = MagicMock()
    tagger.search_album_with_diagnostics.return_value = {"candidates": []}
    tagger.search_item_with_diagnostics.return_value = {"candidates": []}
    monkeypatch.setattr(autotag_worker, "AutoTagger", lambda **k: tagger)
    AutoTagWorker(
        ["a.mp3"], artist_hint="Art", album_hint="Alb (Original Mix)",
        title_hint="Song (Original Mix)", mode=mode,
        regex_cleanup_pattern=r"\s*\(Original Mix\)",
    ).run()
    if mode == "album":
        kw = tagger.search_album_with_diagnostics.call_args.kwargs
        assert kw["album_hint"] == "Alb"
    else:
        kw = tagger.search_item_with_diagnostics.call_args.kwargs
        assert kw["title_hint"] == "Song"
