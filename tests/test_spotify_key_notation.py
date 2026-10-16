"""Key notation for Spotify Audio Features."""

import pytest

from musicorg.core.spotify_features import (
    FeatureMapping,
    SpotifyFeaturesFetcher,
    SpotityFeaturesConfig,
    format_key,
)


@pytest.mark.parametrize(
    "pitch,mode,notation,expected",
    [
        (9, 0, "camelot", "8A"),
        (9, 0, "open_key", "1m"),
        (0, 1, "camelot", "8B"),
        (9, 0, "musical", "Am"),
        (6, 1, "musical", "F#"),
        (-1, 1, "musical", ""),
        (-1, 1, "camelot", ""),
        (-1, 1, "open_key", ""),
    ],
)
def test_format_key(pitch, mode, notation, expected):
    assert format_key(pitch, mode, notation) == expected


def test_config_default_is_musical():
    assert SpotityFeaturesConfig().key_notation == "musical"


def test_non_key_mappings_unchanged():
    # Baseline captured before the change: threshold output for danceability.
    cfg = SpotityFeaturesConfig(feature_mappings=SpotityFeaturesConfig.DEFAULT_MAPPINGS)
    out = SpotifyFeaturesFetcher().resolve_tags({"danceability": 0.8, "energy": 0.1}, cfg)
    assert out == {"comment": "low energy"}


def test_resolve_tags_key_notation():
    m = FeatureMapping(feature_name="key", tag_field="initialkey")
    for notation, exp in (("musical", "Am"), ("camelot", "8A"), ("open_key", "1m")):
        cfg = SpotityFeaturesConfig(feature_mappings=[m], key_notation=notation)
        out = SpotifyFeaturesFetcher().resolve_tags({"key": 9, "mode": 0}, cfg)
        assert out == {"initialkey": exp}


def test_panel_passes_notation(qtbot, monkeypatch):
    from pathlib import Path

    from musicorg.ui import spotify_features_panel as mod

    captured = {}

    class FakeWorker:
        def __init__(self, files, config):
            captured["config"] = config
            raise RuntimeError("stop")

    monkeypatch.setattr(mod, "SpotifyFeaturesWorker", FakeWorker)
    panel = mod.SpotifyFeaturesPanel()
    qtbot.addWidget(panel)
    panel.load_files([Path("a.mp3")])
    panel._key_notation_combo.setCurrentIndex(panel._key_notation_combo.findData("camelot"))
    with pytest.raises(RuntimeError):
        panel._fetch_features()
    assert captured["config"].key_notation == "camelot"


# --- real-file key tag ---------------------------------------------------

from musicorg.core.tagger import TagData, TagManager


def _mp3(tmp_path):
    p = tmp_path / "t.mp3"
    p.write_bytes((bytes([0xFF, 0xFB, 0x90, 0x00]) + b"\x00" * 413) * 3)
    return p


def _flac(tmp_path):
    # fLaC + one last STREAMINFO block: 44.1kHz, 2ch, 16bit, 0 samples
    packed = (44100 << 44) | (1 << 41) | (15 << 36)
    info = (4096).to_bytes(2, "big") * 2 + b"\x00" * 6 + packed.to_bytes(8, "big") + b"\x00" * 16
    p = tmp_path / "t.flac"
    p.write_bytes(b"fLaC" + bytes([0x80, 0, 0, 34]) + info)
    return p


@pytest.fixture(params=["mp3", "flac"])
def audio(request, tmp_path):
    return _mp3(tmp_path) if request.param == "mp3" else _flac(tmp_path)


def test_key_round_trip(audio):
    tm = TagManager()
    tm.write(audio, TagData(title="x", key="8A"))
    assert tm.read(audio).key == "8A"


def test_empty_key_preserves_existing(audio):
    tm = TagManager()
    tm.write(audio, TagData(title="x", key="8A"))
    t = tm.read(audio)
    t.title = "y"
    t.key = ""
    tm.write(audio, t)
    assert tm.read(audio).key == "8A"
    assert tm.read(audio).title == "y"


def test_apply_to_file_writes_camelot(tmp_path, monkeypatch):
    p = _mp3(tmp_path)
    f = SpotifyFeaturesFetcher()
    monkeypatch.setattr(f, "fetch_by_artist_title", lambda a, t, n: {"key": 9, "mode": 0})
    cfg = SpotityFeaturesConfig(
        feature_mappings=[FeatureMapping(feature_name="key", tag_field="key")],
        key_notation="camelot",
        search_by_isrc=False,
    )
    assert f.apply_to_file(p, cfg)
    assert TagManager().read(p).key == "8A"
