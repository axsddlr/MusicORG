"""Auto-Tag apply on real files: panel defaults overwrite, untouched fields survive."""

from __future__ import annotations

import pytest

from musicorg.core.autotagger import AutoTagger, MatchCandidate
from musicorg.core.tagger import TagData, TagManager
from musicorg.ui.autotag_panel import AutoTagPanel
from musicorg.workers.autotag_worker import ApplyMatchWorker
from tests.test_spotify_key_notation import _flac, _mp3


@pytest.fixture(params=["mp3", "flac"])
def audio(request, tmp_path, monkeypatch):
    monkeypatch.setattr(AutoTagger, "_download_artwork_from_urls", classmethod(lambda cls, urls: None))
    p = _mp3(tmp_path) if request.param == "mp3" else _flac(tmp_path)
    TagManager().write(p, TagData(
        title="Wrong Title", artist="Wrong Artist", composer="C",
        comment="keep me", lyrics="la la", key="8A", genre="Techno",
    ))
    return p


SINGLE = {"title": "Right", "artist": "RightA", "album": "RightAlbum", "genre": "House",
          "artwork_urls": ["http://x/a.jpg"]}
ALBUM = {"artist": "RightA", "album": "RightAlbum", "genre": "House", "artwork_urls": [],
         "tracks": [{"title": "Right", "artist": "RightA", "track": 1, "disc": 1}]}


def _panel_defaults(qtbot):
    panel = AutoTagPanel()
    qtbot.addWidget(panel)
    return panel._get_overwrite_fields(), panel._fill_empty.isChecked()


def _run(path, payload, overwrite_fields, fill_empty_only):
    w = ApplyMatchWorker([path], MatchCandidate(raw_match=payload),
                         overwrite_fields=overwrite_fields, fill_empty_only=fill_empty_only)
    results = []
    w.finished.connect(results.append)
    w.run()
    assert results == [True]
    return TagManager().read(path)


def _assert_preserved(t):
    assert (t.composer, t.comment, t.lyrics, t.key) == ("C", "keep me", "la la", "8A")


@pytest.mark.parametrize("payload", [SINGLE, ALBUM], ids=["single", "album"])
def test_panel_default_apply_overwrites_and_preserves(qtbot, audio, payload):
    fields, fill = _panel_defaults(qtbot)
    t = _run(audio, payload, fields, fill)
    assert (t.title, t.artist, t.genre, t.album) == ("Right", "RightA", "House", "RightAlbum")
    _assert_preserved(t)


@pytest.mark.parametrize("payload", [SINGLE, ALBUM], ids=["single", "album"])
def test_fill_empty_only_keeps_set_fills_empty(qtbot, audio, payload):
    t = _run(audio, payload, None, True)
    assert (t.title, t.artist, t.genre) == ("Wrong Title", "Wrong Artist", "Techno")
    assert t.album == "RightAlbum"
    _assert_preserved(t)


@pytest.mark.parametrize("payload", [SINGLE, ALBUM], ids=["single", "album"])
def test_selected_fields_preserve_rest(qtbot, audio, payload):
    t = _run(audio, payload, ["title"], False)
    assert (t.title, t.artist, t.genre) == ("Right", "Wrong Artist", "Techno")
    _assert_preserved(t)
