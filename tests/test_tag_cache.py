"""Tests for musicorg.core.tag_cache."""

from pathlib import Path

from musicorg.core.tag_cache import TagCache
from musicorg.core.tagger import TagData


def test_put_and_get_hit(tmp_path):
    db_path = tmp_path / "tag_cache.db"
    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"abc")
    tags = TagData(
        title="Song",
        artist="Artist",
        album="Album",
        track=3,
        duration=123.4,
        artwork_data=b"\x01\x02",
        artwork_mime="image/png",
    )

    cache = TagCache(db_path)
    cache.open()
    cache.put(audio_path, 111, 222, tags)

    hit = cache.get(audio_path, 111, 222)
    cache.close()

    assert hit is not None
    assert hit.title == "Song"
    assert hit.artist == "Artist"
    assert hit.album == "Album"
    assert hit.track == 3
    assert hit.duration == 123.4
    assert hit.artwork_data == b"\x01\x02"
    assert hit.artwork_mime == "image/png"


def test_get_miss_when_fingerprint_changes(tmp_path):
    db_path = tmp_path / "tag_cache.db"
    audio_path = tmp_path / "song.flac"
    audio_path.write_bytes(b"data")

    cache = TagCache(db_path)
    cache.open()
    cache.put(audio_path, 100, 200, TagData(title="Before"))

    assert cache.get(audio_path, 101, 200) is None
    assert cache.get(audio_path, 100, 201) is None
    cache.close()


def test_put_many_and_invalidate_many(tmp_path):
    db_path = tmp_path / "tag_cache.db"
    paths = [tmp_path / "a.mp3", tmp_path / "b.mp3", tmp_path / "c.mp3"]
    for p in paths:
        p.write_bytes(b"x")

    entries = [
        (paths[0], 1, 10, TagData(title="A")),
        (paths[1], 2, 20, TagData(title="B")),
        (paths[2], 3, 30, TagData(title="C")),
    ]

    cache = TagCache(db_path)
    cache.open()
    cache.put_many(entries)
    cache.invalidate_many([paths[0], paths[2]])

    assert cache.get(paths[0], 1, 10) is None
    hit = cache.get(paths[1], 2, 20)
    assert hit is not None
    assert hit.title == "B"
    assert cache.get(paths[2], 3, 30) is None
    cache.close()


def test_clear_removes_all_entries(tmp_path):
    db_path = tmp_path / "tag_cache.db"
    audio_path = Path(tmp_path / "song.mp3")
    audio_path.write_bytes(b"xyz")

    cache = TagCache(db_path)
    cache.open()
    cache.put(audio_path, 9, 9, TagData(title="Song"))
    assert cache.get(audio_path, 9, 9) is not None

    cache.clear()
    assert cache.get(audio_path, 9, 9) is None
    cache.close()
