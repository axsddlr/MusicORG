"""Auto-Tag panel wiring: hints, duration/ISRC, strictness, Shazam, apply options, profiles."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from musicorg.core import autotagger as autotagger_mod
from musicorg.core import tagger as tagger_mod
from musicorg.core.autotagger import AutoTagger
from musicorg.core.tagger import TagData
from musicorg.ui import autotag_panel
from musicorg.ui.autotag_panel import AutoTagPanel
from musicorg.workers.base_worker import BaseWorker


def _fake_worker_cls(payload, calls):
    class _Fake(BaseWorker):
        def __init__(self, *args, **kwargs):
            super().__init__()
            calls.append(SimpleNamespace(args=args, kwargs=kwargs))

        def run(self):
            self.finished.emit(payload)

    return _Fake


def _fake_tag_manager(monkeypatch, tags: TagData):
    class _TM:
        def read(self, path):
            return tags

    monkeypatch.setattr(tagger_mod, "TagManager", _TM)


@pytest.fixture
def panel(qtbot):
    p = AutoTagPanel()
    qtbot.addWidget(p)
    yield p
    p.shutdown()


@pytest.fixture
def search_calls(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        autotag_panel, "AutoTagWorker",
        _fake_worker_cls({"candidates": [], "source_errors": {}, "source_counts": {}}, calls),
    )
    return calls


def _search_single(qtbot, panel):
    panel._search_single_btn.click()
    qtbot.waitUntil(lambda: panel._search_thread is None)


def test_filename_hint_fill_when_tags_empty(panel, monkeypatch):
    _fake_tag_manager(monkeypatch, TagData())
    panel.load_files([Path("Some Artist - Some Title.mp3")])
    assert panel._artist_edit.text() == "Some Artist"
    assert panel._title_edit.text() == "Some Title"


def test_tags_win_over_filename(panel, monkeypatch):
    _fake_tag_manager(monkeypatch, TagData(artist="Tag A", title="Tag T"))
    panel.load_files([Path("Some Artist - Some Title.mp3")])
    assert panel._artist_edit.text() == "Tag A"
    assert panel._title_edit.text() == "Tag T"


def test_duration_and_isrc_reach_worker(qtbot, panel, monkeypatch, search_calls):
    _fake_tag_manager(monkeypatch, TagData(artist="A", title="T", duration=215.6, isrc="USX1"))
    panel.load_files([Path("a.mp3")])
    _search_single(qtbot, panel)
    kw = search_calls[-1].kwargs
    assert kw["duration_hint"] == 215
    assert kw["isrc"] == "USX1"


def test_zero_duration_is_none(qtbot, panel, monkeypatch, search_calls):
    _fake_tag_manager(monkeypatch, TagData(artist="A", title="T"))
    panel.load_files([Path("a.mp3")])
    _search_single(qtbot, panel)
    kw = search_calls[-1].kwargs
    assert kw["duration_hint"] is None
    assert not kw["isrc"]


@pytest.mark.parametrize("pct,expected", [(0, None), (80, 0.2)])
def test_strictness_to_max_distance(qtbot, panel, monkeypatch, search_calls, pct, expected):
    _fake_tag_manager(monkeypatch, TagData(artist="A", title="T"))
    panel.load_files([Path("a.mp3")])
    panel._min_match_spin.setValue(pct)
    _search_single(qtbot, panel)
    md = search_calls[-1].kwargs["max_distance"]
    if expected is None:
        assert md is None
    else:
        assert md == pytest.approx(expected)


def test_worker_passes_new_search_args(qtbot, monkeypatch):
    from musicorg.workers import autotag_worker

    tagger = MagicMock()
    tagger.search_item_with_diagnostics.return_value = {"candidates": []}
    ctor = MagicMock(return_value=tagger)
    monkeypatch.setattr(autotag_worker, "AutoTagger", ctor)
    autotag_worker.AutoTagWorker(
        ["a.mp3"], mode="single", duration_hint=200, isrc="I1", max_distance=0.3,
    ).run()
    assert ctor.call_args.kwargs["max_distance"] == 0.3
    kw = tagger.search_item_with_diagnostics.call_args.kwargs
    assert kw["duration_hint"] == 200
    assert kw["isrc"] == "I1"


def test_apply_options_reach_apply_worker(qtbot, panel, monkeypatch):
    calls: list = []
    monkeypatch.setattr(autotag_panel, "ApplyMatchWorker", _fake_worker_cls(True, calls))
    _fake_tag_manager(monkeypatch, TagData(artist="A", title="T"))
    panel.load_files([Path("a.mp3")])
    panel._match_list.selected_candidate = lambda: MagicMock()
    panel._merge_genres_cb.setChecked(True)
    panel._id3v23_cb.setChecked(True)
    panel._apply_match()
    qtbot.waitUntil(lambda: panel._apply_thread is None)
    kw = calls[-1].kwargs
    assert kw["merge_genres"] is True
    assert kw["id3_version"] == 3


def test_apply_worker_forwards_options(qtbot, monkeypatch):
    from musicorg.workers import autotag_worker

    tagger = MagicMock()
    monkeypatch.setattr(autotag_worker, "AutoTagger", lambda **k: tagger)
    autotag_worker.ApplyMatchWorker(
        ["a.mp3"], MagicMock(), overwrite_fields=None, fill_empty_only=False,
        merge_genres=True, id3_version=3,
    ).run()
    kw = tagger.apply_match.call_args.kwargs
    assert kw == {"merge_genres": True, "id3_version": 3}
    autotag_worker.ApplyMatchWorker(
        ["a.mp3"], MagicMock(), overwrite_fields=["genre"], merge_genres=True, id3_version=3,
    ).run()
    kw = tagger.apply_match_with_overrides.call_args.kwargs
    assert kw["merge_genres"] is True and kw["id3_version"] == 3


class _RecordingTM:
    def __init__(self):
        self.writes: list = []

    def read(self, path):
        return TagData(genre="Techno")

    def write(self, path, tags, id3_version=4):
        self.writes.append((tags, id3_version))


@pytest.mark.parametrize("use_overrides", [False, True])
@pytest.mark.parametrize("album", [False, True])
def test_core_apply_merge_genres_and_id3(monkeypatch, use_overrides, album):
    tm = _RecordingTM()
    monkeypatch.setattr(autotagger_mod, "TagManager", lambda: tm)
    monkeypatch.setattr(AutoTagger, "_download_artwork_from_urls", lambda self, urls: None)
    payload = {"title": "T", "artist": "A", "album": "Al", "genre": "House", "artwork_urls": []}
    if album:
        payload["tracks"] = [{"title": "T", "track": 1}]
    match = SimpleNamespace(raw_match=payload)
    at = AutoTagger()
    if use_overrides:
        ok = at.apply_match_with_overrides(
            ["a.mp3"], match, overwrite_fields=["genre"], fill_empty_only=False,
            merge_genres=True, id3_version=3,
        )
    else:
        ok = at.apply_match(["a.mp3"], match, merge_genres=True, id3_version=3)
    assert ok
    tags, ver = tm.writes[-1]
    assert tags.genre == "Techno; House"
    assert ver == 3
    # default: no merge, ID3v2.4
    at.apply_match(["a.mp3"], match)
    tags, ver = tm.writes[-1]
    assert tags.genre == "House"
    assert ver == 4


def test_shazam_fills_hints_and_isrc(qtbot, panel, monkeypatch, search_calls):
    shazam_calls: list = []
    payload = {
        "results": [{"path": "a.mp3", "artist": "SA", "title": "ST", "isrc": "SZ1"}],
        "errors": [],
    }
    monkeypatch.setattr(autotag_panel, "ShazamWorker", _fake_worker_cls(payload, shazam_calls))
    _fake_tag_manager(monkeypatch, TagData(artist="A", title="T"))
    panel.load_files([Path("a.mp3")])
    assert panel._shazam_btn.isEnabled()
    panel._shazam_btn.click()
    qtbot.waitUntil(lambda: panel._shazam_thread is None)
    assert shazam_calls[-1].args[0] == [Path("a.mp3")]
    assert panel._artist_edit.text() == "SA"
    assert panel._title_edit.text() == "ST"
    _search_single(qtbot, panel)
    assert search_calls[-1].kwargs["isrc"] == "SZ1"


def test_shazam_errors_shown(qtbot, panel, monkeypatch):
    payload = {"results": [], "errors": ["No match: a.mp3"]}
    monkeypatch.setattr(autotag_panel, "ShazamWorker", _fake_worker_cls(payload, []))
    _fake_tag_manager(monkeypatch, TagData(artist="A", title="T"))
    panel.load_files([Path("a.mp3")])
    panel._shazam_btn.click()
    qtbot.waitUntil(lambda: panel._shazam_thread is None)
    assert "No match" in panel._source_status_label.text()


def test_shazam_disabled_without_shazamio(qtbot, monkeypatch):
    monkeypatch.setattr(autotag_panel, "_shazam_available", lambda: False)
    p = AutoTagPanel()
    qtbot.addWidget(p)
    p._files = [Path("a.mp3")]
    p._refresh_search_controls()
    assert not p._shazam_btn.isEnabled()
    assert "shazamio" in p._shazam_btn.toolTip()


def _set_controls(p, *, alt: bool):
    p._source_mb.setChecked(not alt)
    p._source_discogs.setChecked(alt)
    p._source_beatport.setChecked(alt)
    p._source_traxsource.setChecked(alt)
    p._overwrite_all.setChecked(not alt)
    for name in ("title", "artist", "album", "albumartist", "track", "disc", "year", "genre", "artwork"):
        getattr(p, f"_overwrite_{name}").setChecked(not alt or name in ("title", "genre"))
    p._fill_empty.setChecked(not alt)
    p._cleanup_pattern_edit.setText(r"\s+\(x\)" if alt else "")
    p._cleanup_replace_edit.setText("y" if alt else "")
    p._min_match_spin.setValue(70 if alt else 0)
    p._merge_genres_cb.setChecked(alt)
    p._id3v23_cb.setChecked(alt)


def _snapshot(p):
    names = ("title", "artist", "album", "albumartist", "track", "disc", "year", "genre", "artwork")
    return (
        p._source_mb.isChecked(), p._source_discogs.isChecked(),
        p._source_beatport.isChecked(), p._source_traxsource.isChecked(),
        p._overwrite_all.isChecked(),
        tuple(getattr(p, f"_overwrite_{n}").isChecked() for n in names),
        p._fill_empty.isChecked(), p._cleanup_pattern_edit.text(), p._cleanup_replace_edit.text(),
        p._min_match_spin.value(), p._merge_genres_cb.isChecked(), p._id3v23_cb.isChecked(),
    )


def test_profile_save_load_restores_controls(qtbot, panel, tmp_path):
    panel.set_profile_dir(tmp_path)
    _set_controls(panel, alt=True)
    saved = _snapshot(panel)
    panel._profile_combo.setEditText("Mine")
    panel._profile_save_btn.click()
    _set_controls(panel, alt=False)
    assert _snapshot(panel) != saved
    idx = panel._profile_combo.findText("Mine")
    assert idx >= 0
    panel._profile_combo.setCurrentIndex(idx)
    panel._profile_combo.activated.emit(idx)
    assert _snapshot(panel) == saved

    # persisted to disk: a fresh panel sees and restores it
    other = AutoTagPanel()
    qtbot.addWidget(other)
    other.set_profile_dir(tmp_path)
    idx = other._profile_combo.findText("Mine")
    other._profile_combo.setCurrentIndex(idx)
    other._profile_combo.activated.emit(idx)
    assert _snapshot(other) == saved

    # delete
    panel._profile_combo.setCurrentIndex(panel._profile_combo.findText("Mine"))
    panel._profile_delete_btn.click()
    assert panel._profile_combo.findText("Mine") == -1
