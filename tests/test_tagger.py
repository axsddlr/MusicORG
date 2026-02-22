"""Tests for musicorg.core.tagger."""

from pathlib import Path

import pytest

from musicorg.core.tagger import TagData, TagManager


class TestTagData:
    def test_defaults(self):
        td = TagData()
        assert td.title == ""
        assert td.artist == ""
        assert td.track == 0
        assert td.comment == ""
        assert td.lyrics == ""
        assert td.artwork_data is None
        assert td.artwork_mime == ""

    def test_as_dict(self):
        td = TagData(
            title="Song",
            artist="Band",
            track=5,
            comment="A comment",
            lyrics="Some lyrics",
            artwork_data=b"\x01\x02",
            artwork_mime="image/png",
        )
        d = td.as_dict()
        assert d["title"] == "Song"
        assert d["artist"] == "Band"
        assert d["track"] == 5
        assert d["comment"] == "A comment"
        assert d["lyrics"] == "Some lyrics"
        assert d["artwork_data"] == b"\x01\x02"
        assert d["artwork_mime"] == "image/png"


class TestTagManager:
    @pytest.fixture
    def sample_mp3(self, tmp_path):
        """Create a minimal valid MP3 file for testing."""
        # Create a minimal MP3 frame (MPEG1 Layer3, 128kbps, 44100Hz, stereo)
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

    def test_read_invalid_file_returns_empty_tag_data(self, tmp_path):
        """Unreadable / corrupted files should return an empty TagData."""
        p = tmp_path / "garbage.mp3"
        p.write_bytes(b"\x00" * 100)
        tm = TagManager()
        tags = tm.read(p)
        assert isinstance(tags, TagData)

    def test_read_unknown_extension_returns_empty_tag_data(self, tmp_path):
        """Unknown extensions should return an empty TagData gracefully."""
        p = tmp_path / "test.xyz"
        p.write_bytes(b"\x00" * 100)
        tm = TagManager()
        tags = tm.read(p)
        assert isinstance(tags, TagData)

    def test_write_invalid_file_raises_value_error(self, tmp_path):
        """Writing to a file that cannot be loaded raises ValueError."""
        p = tmp_path / "test.xyz"
        p.write_bytes(b"\x00" * 100)
        tm = TagManager()
        with pytest.raises(ValueError):
            tm.write(p, TagData())
