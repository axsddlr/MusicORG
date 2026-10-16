"""Duration-aware scoring, strictness filtering and ISRC-first lookup (no network)."""

from __future__ import annotations

import pytest

from musicorg.core.autotagger import AutoTagger, MatchCandidate


def _cand(title: str, distance: float, length: int, source: str = "MusicBrainz") -> MatchCandidate:
    return MatchCandidate(
        source=source,
        artist="A",
        album=title,
        distance=distance,
        tracks=[{"track": 0, "disc": 0, "title": title, "artist": "A", "length": length}],
        raw_match={"source": source, "title": title, "length": length},
    )


@pytest.mark.parametrize(
    "hint,cand,expected",
    [
        (100, 100, 0.0),
        (100, 103, 0.0),
        (100, 97, 0.0),
        (100, 130, 0.3),
        (100, 160, 0.3),
        (None, 100, 0.0),
        (100, None, 0.0),
        (100, 0, 0.0),
        (0, 100, 0.0),
    ],
)
def test_duration_penalty_bounds(hint, cand, expected):
    assert AutoTagger._duration_penalty(hint, cand) == expected


def test_duration_penalty_midpoint():
    assert AutoTagger._duration_penalty(100, 116.5) == pytest.approx(0.15)


@pytest.fixture
def audio(tmp_path):
    p = tmp_path / "a.mp3"
    p.write_bytes(b"x")
    return p


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(AutoTagger, "_mb_artwork_urls", classmethod(lambda cls, a, b: []))


def _tagger(monkeypatch, mb_results, **kw):
    t = AutoTagger(enabled_sources=["MusicBrainz"], **kw)
    monkeypatch.setattr(t, "_search_item_mb", lambda artist, title: list(mb_results))
    return t


def test_duration_reranks(monkeypatch, audio):
    good_text_bad_len = _cand("close", 0.05, 400)
    ok_text_right_len = _cand("right", 0.10, 200)
    t = _tagger(monkeypatch, [good_text_bad_len, ok_text_right_len])
    out = t.search_item_with_diagnostics(audio, "A", "T", duration_hint=200)["candidates"]
    assert [c.album for c in out] == ["right", "close"]
    assert out[1].distance == pytest.approx(0.35)


def test_no_hint_keeps_order(monkeypatch, audio):
    t = _tagger(monkeypatch, [_cand("close", 0.05, 400), _cand("right", 0.10, 200)])
    out = t.search_item_with_diagnostics(audio, "A", "T")["candidates"]
    assert [c.album for c in out] == ["close", "right"]


def test_strictness_item_and_album(monkeypatch, audio):
    t = _tagger(monkeypatch, [_cand("a", 0.1, 0), _cand("b", 0.5, 0)], max_distance=0.2)
    out = t.search_item_with_diagnostics(audio, "A", "T")["candidates"]
    assert [c.album for c in out] == ["a"]

    monkeypatch.setattr(t, "_search_album_mb", lambda artist, album: [_cand("a", 0.1, 0), _cand("b", 0.5, 0)])
    out = t.search_album_with_diagnostics([audio], "A", "Al")["candidates"]
    assert [c.album for c in out] == ["a"]


def test_default_no_strictness(monkeypatch, audio):
    t = _tagger(monkeypatch, [_cand("b", 0.99, 0)])
    assert len(t.search_item_with_diagnostics(audio, "A", "T")["candidates"]) == 1


_ISRC_PAYLOAD = {
    "isrc": {
        "id": "USX",
        "recording-list": [
            {
                "id": "rec1",
                "title": "Exact",
                "length": "200000",
                "artist-credit": [{"artist": {"name": "Art"}}],
                "release-list": [{"id": "rel1", "title": "Alb", "date": "2020-01-01"}],
            }
        ],
    }
}


def test_isrc_first(monkeypatch, audio):
    import musicbrainzngs

    monkeypatch.setattr(musicbrainzngs, "get_recordings_by_isrc", lambda isrc, includes=None: _ISRC_PAYLOAD)
    t = _tagger(monkeypatch, [_cand("text", 0.0, 0)])
    out = t.search_item_with_diagnostics(audio, "A", "T", duration_hint=10, isrc="USX")["candidates"]
    assert out[0].album == "Alb"
    assert out[0].distance == 0.0
    assert out[0].tracks[0]["title"] == "Exact"
    assert out[1].album == "text"


def test_isrc_error_falls_back(monkeypatch, audio):
    import musicbrainzngs

    def boom(isrc, includes=None):
        raise RuntimeError("offline")

    monkeypatch.setattr(musicbrainzngs, "get_recordings_by_isrc", boom)
    t = _tagger(monkeypatch, [_cand("text", 0.3, 0)])
    out = t.search_item_with_diagnostics(audio, "A", "T", isrc="USX")["candidates"]
    assert [c.album for c in out] == ["text"]


def test_isrc_empty_falls_back(monkeypatch, audio):
    import musicbrainzngs

    monkeypatch.setattr(
        musicbrainzngs, "get_recordings_by_isrc", lambda isrc, includes=None: {"isrc": {"recording-list": []}}
    )
    t = _tagger(monkeypatch, [_cand("text", 0.3, 0)])
    out = t.search_item_with_diagnostics(audio, "A", "T", isrc="USX")["candidates"]
    assert [c.album for c in out] == ["text"]


def test_isrc_dedupes_text_results(monkeypatch, audio):
    import musicbrainzngs

    rec = _ISRC_PAYLOAD["isrc"]["recording-list"][0]
    other = dict(rec, id="rec-2", title="Other")
    isrc_rec = dict(rec, id="rec-1")
    monkeypatch.setattr(
        musicbrainzngs,
        "get_recordings_by_isrc",
        lambda isrc, includes=None: {"isrc": {"recording-list": [isrc_rec]}},
    )
    monkeypatch.setattr(
        musicbrainzngs,
        "search_recordings",
        lambda **kw: {"recording-list": [dict(isrc_rec, **{"ext:score": "90"}), dict(other, **{"ext:score": "80"})]},
    )
    t = AutoTagger(enabled_sources=["MusicBrainz"])
    out = t.search_item_with_diagnostics(audio, "A", "T", isrc="USX")["candidates"]
    ids = [c.raw_match["recording_id"] for c in out]
    assert ids == ["rec-1", "rec-2"]
    assert out[0].distance == 0.0
