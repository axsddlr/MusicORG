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

    def test_read_artwork_uses_raw_and_mime_attributes(self, monkeypatch):
        class _Artwork:
            def __init__(self):
                self.raw = b"\x89PNGdata"
                self.mime = "image/png"

        class _Field:
            def __init__(self, first):
                self.first = first

        class _File:
            def __getitem__(self, key):
                if key == "artwork":
                    return _Field(_Artwork())
                return _Field(None)

        monkeypatch.setattr(
            "musicorg.core.tagger.music_tag.load_file",
            lambda _path: _File(),
        )

        tm = TagManager()
        tags = tm.read("dummy.mp3")
        assert tags.artwork_data == b"\x89PNGdata"
        assert tags.artwork_mime == "image/png"

    def test_write_artwork_uses_fmt_constructor_when_available(self, monkeypatch):
        calls = []

        class _File:
            def __setitem__(self, key, value):
                calls.append((key, value))

            def save(self):
                calls.append(("save", None))

        class _Artwork:
            def __init__(self, **kwargs):
                calls.append(("artwork", kwargs))

        monkeypatch.setattr(
            "musicorg.core.tagger.music_tag.load_file",
            lambda _path: _File(),
        )
        monkeypatch.setattr("musicorg.core.tagger.music_tag.Artwork", _Artwork)

        tm = TagManager()
        tm.write(
            "dummy.mp3",
            TagData(artwork_data=b"\x01\x02", artwork_mime="image/png"),
        )

        artwork_calls = [call for call in calls if call[0] == "artwork"]
        assert artwork_calls
        assert artwork_calls[0][1].get("fmt") == "png"

    def test_write_artwork_failure_raises_value_error(self, monkeypatch):
        class _File:
            def __setitem__(self, key, value):
                if key == "artwork":
                    raise RuntimeError("cannot embed")

            def save(self):
                raise AssertionError("save should not be called when artwork fails")

        class _Artwork:
            def __init__(self, **kwargs):
                _ = kwargs

        monkeypatch.setattr(
            "musicorg.core.tagger.music_tag.load_file",
            lambda _path: _File(),
        )
        monkeypatch.setattr("musicorg.core.tagger.music_tag.Artwork", _Artwork)

        tm = TagManager()
        with pytest.raises(ValueError, match="Failed to embed artwork"):
            tm.write(
                "dummy.mp3",
                TagData(artwork_data=b"\x01\x02", artwork_mime="image/png"),
            )
