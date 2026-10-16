"""Tests for musicorg.core.tag_options and the tagger id3_version option."""

import pytest
from mutagen.id3 import ID3

from musicorg.core.tag_options import (
    capitalize_genre,
    key_from_pitch_class,
    merge_genres,
    to_camelot,
    to_open_key,
)
from musicorg.core.tagger import TagData, TagManager

# Full table in fifths order (C, G, D, ...): major Camelot B, minor A.
_MAJ = ["C", "G", "D", "A", "E", "B", "F#", "C#", "G#", "D#", "A#", "F"]
_MIN = ["A", "E", "B", "F#", "C#", "G#", "D#", "A#", "F", "C", "G", "D"]


@pytest.mark.parametrize("i", range(12))
def test_full_table(i):
    n = (8 - 1 + i) % 12 + 1  # C=8B, then +1 per fifth
    assert to_camelot(_MAJ[i]) == f"{n}B"
    assert to_camelot(_MIN[i] + "m") == f"{n}A"
    od = (i % 12) + 1
    assert to_open_key(_MAJ[i]) == f"{od}d"
    assert to_open_key(_MIN[i] + "m") == f"{od}m"


@pytest.mark.parametrize("key,exp", [
    ("C", "8B"), ("Am", "8A"), ("A min", "8A"), ("A minor", "8A"), ("A Minor", "8A"),
    ("G", "9B"), ("Em", "9A"), ("F", "7B"), ("Dm", "7A"),
    ("F#", "2B"), ("Gb major", "2B"), ("F# maj", "2B"), ("D#m", "2A"), ("Ebm", "2A"),
    ("B", "1B"), ("G#m", "1A"), ("Bbm", "3A"), ("C♯ minor", "12A"),
    ("D♭ Major", "3B"), ("8A", "8A"), ("8a", "8A"), ("1m", "8A"), ("1d", "8B"),
])
def test_camelot(key, exp):
    assert to_camelot(key) == exp


def test_open_key():
    assert to_open_key("C") == "1d"
    assert to_open_key("Am") == "1m"
    assert to_open_key("G") == "2d"
    assert to_open_key("8A") == "1m"
    assert to_open_key("1m") == "1m"
    assert to_camelot(to_open_key("8A")) == "8A"


@pytest.mark.parametrize("bad", ["", "garbage", "H", "13A", "0B", "Xm", None])
def test_garbage(bad):
    assert to_camelot(bad) is None
    assert to_open_key(bad) is None


def test_pitch_class():
    assert key_from_pitch_class(9, 0) == "Am"
    assert to_camelot(key_from_pitch_class(9, 0)) == "8A"
    assert key_from_pitch_class(0, 1) == "C"
    assert key_from_pitch_class(6, 1) == "F#"
    assert key_from_pitch_class(-1, 1) is None
    assert key_from_pitch_class(3, -1) is None
    assert key_from_pitch_class(12, 1) is None


def test_merge_genres():
    assert merge_genres("House; Techno", "techno, Deep House") == "House; Techno; Deep House"
    assert merge_genres("", "A/B") == "A; B"
    assert merge_genres("A", "", separator=", ") == "A"
    assert merge_genres("a ; ;b", "B") == "a; b"


def test_capitalize_genre():
    assert capitalize_genre("deep house") == "Deep House"
    assert capitalize_genre("EDM") == "EDM"
    assert capitalize_genre("uk garage") == "Uk Garage"
    assert capitalize_genre("UK garage") == "UK Garage"
    assert capitalize_genre("DnB") == "DnB"
    assert capitalize_genre("drum and bass") == "Drum and Bass"
    assert capitalize_genre("rock n roll") == "Rock n Roll"
    assert capitalize_genre("and so") == "And So"
    assert capitalize_genre("") == ""


@pytest.fixture
def sample_mp3(tmp_path):
    p = tmp_path / "t.mp3"
    p.write_bytes((bytes([0xFF, 0xFB, 0x90, 0x00]) + b"\x00" * 413) * 3)
    return p


def test_id3_default_is_v24(sample_mp3):
    TagManager().write(sample_mp3, TagData(title="x"))
    assert ID3(sample_mp3).version[:2] == (2, 4)


def test_id3_v23(sample_mp3):
    TagManager().write(sample_mp3, TagData(title="x"), id3_version=3)
    assert ID3(sample_mp3).version[:2] == (2, 3)
