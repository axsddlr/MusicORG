"""Tests for musicorg.core.tagger."""

import shutil
from pathlib import Path

import pytest
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3

from musicorg.core.tagger import TagData, TagManager, _first, _first_int


class TestHelpers:
    def test_first_with_list(self):
        assert _first({"key": ["val1", "val2"]}, "key") == "val1"

    def test_first_with_string(self):
        assert _first({"key": "val"}, "key") == "val"

    def test_first_missing(self):
        assert _first({}, "key") == ""

    def test_first_default(self):
        assert _first({}, "key", "default") == "default"

    def test_first_int_simple(self):
        assert _first_int({"tracknumber": ["3"]}, "tracknumber") == 3

    def test_first_int_with_total(self):
        assert _first_int({"tracknumber": ["3/12"]}, "tracknumber") == 3

    def test_first_int_missing(self):
        assert _first_int({}, "tracknumber") == 0

    def test_first_int_invalid(self):
        assert _first_int({"tracknumber": ["abc"]}, "tracknumber") == 0


class TestTagData:
    def test_defaults(self):
        td = TagData()
        assert td.title == ""
        assert td.artist == ""
        assert td.track == 0

    def test_as_dict(self):
        td = TagData(title="Song", artist="Band", track=5)
        d = td.as_dict()
        assert d["title"] == "Song"
        assert d["artist"] == "Band"
        assert d["track"] == 5


class TestTagManager:
    @pytest.fixture
    def sample_mp3(self, tmp_path):
        """Create a minimal valid MP3 file for testing."""
        # Create a minimal MP3 frame (MPEG1 Layer3, 128kbps, 44100Hz, stereo)
        # Sync word + valid header
        header = bytes([
            0xFF, 0xFB, 0x90, 0x00,  # MPEG1, Layer3, 128kbps, 44100Hz
        ])
        # Pad to make a valid frame (417 bytes for 128kbps/44100Hz)
        frame = header + b"\x00" * 413
        p = tmp_path / "test.mp3"
        p.write_bytes(frame * 3)  # Write a few frames
        return p

    def test_read_returns_tag_data(self, sample_mp3):
        tm = TagManager()
        tags = tm.read(sample_mp3)
        assert isinstance(tags, TagData)

    def test_read_unsupported_format(self, tmp_path):
        p = tmp_path / "test.wav"
        p.write_bytes(b"\x00" * 100)
        tm = TagManager()
        with pytest.raises(ValueError, match="Unsupported format"):
            tm.read(p)

    def test_write_unsupported_format(self, tmp_path):
        p = tmp_path / "test.wav"
        p.write_bytes(b"\x00" * 100)
        tm = TagManager()
        with pytest.raises(ValueError, match="Unsupported format"):
            tm.write(p, TagData())
