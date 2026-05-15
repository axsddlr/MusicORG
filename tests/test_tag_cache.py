"""Tests for musicorg.core.tag_cache."""

from pathlib import Path

import pytest

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


def test_concurrent_put_and_get(tmp_path):
    """Stress-test TagCache with concurrent readers and writers."""
    import threading

    db_path = tmp_path / "concurrent_cache.db"
    errors: list[str] = []

    cache = TagCache(db_path)
    cache.open()
    paths = [tmp_path / f"f{i}.mp3" for i in range(20)]
    for p in paths:
        p.write_bytes(b"x")

    def writer(pid: int) -> None:
        try:
            for i in range(5):
                idx = pid * 5 + i
                if idx < len(paths):
                    cache.put(paths[idx], idx, idx + 100, TagData(title=f"W{pid}-{i}"))
        except Exception as e:
            errors.append(f"writer {pid}: {e}")

    def reader(pid: int) -> None:
        try:
            for idx in range(len(paths)):
                cache.get(paths[idx], idx, idx + 100)
        except Exception as e:
            errors.append(f"reader {pid}: {e}")

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
    threads += [threading.Thread(target=reader, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    cache.close()
    assert not errors, f"Concurrent errors: {errors}"


def test_double_close_is_safe(tmp_path):
    db_path = tmp_path / "safe.db"
    cache = TagCache(db_path)
    cache.open()
    cache.close()
    cache.close()


def test_get_before_open_raises(tmp_path):
    db_path = tmp_path / "never_open.db"
    cache = TagCache(db_path)
    with pytest.raises(RuntimeError, match="not open"):
        cache.get(Path("f.mp3"), 1, 1)
