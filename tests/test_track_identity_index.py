"""Tests for persistent track identity index."""

from pathlib import Path

import pytest

from musicorg.core.tagger import TagData
from musicorg.core.track_identity_index import TrackIdentityIndex, build_identity_fields


def test_build_identity_fields_uses_sha1_uid_when_present(tmp_path):
    path = tmp_path / "song.mp3"
    tags = TagData(title="Song", artist="Artist", album="Album", track=1)
    track_uid, strict_key, loose_key, title_key, duration = build_identity_fields(
        path,
        tags,
        content_sha1="abc123",
    )
    assert track_uid == "sha1:abc123"
    assert "song" in strict_key
    assert title_key == "song"
    assert duration == 0.0


def test_track_identity_index_roundtrip(tmp_path):
    db_path = tmp_path / "identity.db"
    file_path = tmp_path / "Artist" / "Album" / "01 Song.mp3"
    file_path.parent.mkdir(parents=True)

    idx = TrackIdentityIndex(db_path)
    idx.open()
    rec = idx.upsert(
        file_path,
        mtime_ns=123,
        size=456,
        tags=TagData(title="Song", artist="Artist", album="Album", track=1),
    )
    fetched = idx.get(file_path, 123, 456)
    idx.close()

    assert fetched is not None
    assert fetched.track_uid == rec.track_uid
    assert fetched.strict_identity_key == rec.strict_identity_key


def test_track_identity_index_preserves_sha1_for_same_fingerprint(tmp_path):
    db_path = tmp_path / "identity.db"
    file_path = tmp_path / "track.mp3"

    idx = TrackIdentityIndex(db_path)
    idx.open()
    idx.upsert(file_path, 10, 20, tags=TagData(title="A"), content_sha1="deadbeef")
    rec = idx.upsert(file_path, 10, 20, tags=TagData(title="A"))
    idx.close()

    assert rec.content_sha1 == "deadbeef"
    assert rec.track_uid == "sha1:deadbeef"


def test_track_identity_index_keeps_richer_identity_for_same_fingerprint(tmp_path):
    db_path = tmp_path / "identity.db"
    file_path = tmp_path / "Artist" / "Album" / "track.mp3"
    file_path.parent.mkdir(parents=True)

    idx = TrackIdentityIndex(db_path)
    idx.open()
    first = idx.upsert(
        file_path,
        mtime_ns=99,
        size=1234,
        tags=TagData(title="Song", artist="Artist", album="Album", track=1),
    )
    second = idx.upsert(
        file_path,
        mtime_ns=99,
        size=1234,
        tags=TagData(),
    )
    idx.close()

    assert second.strict_identity_key == first.strict_identity_key
    assert second.loose_identity_key == first.loose_identity_key
    assert second.title_key == first.title_key


def test_track_identity_index_promotes_sha1_without_dropping_identity(tmp_path):
    db_path = tmp_path / "identity.db"
    file_path = tmp_path / "Artist" / "Album" / "track.mp3"
    file_path.parent.mkdir(parents=True)

    idx = TrackIdentityIndex(db_path)
    idx.open()
    first = idx.upsert(
        file_path,
        mtime_ns=77,
        size=456,
        tags=TagData(title="Song", artist="Artist", album="Album", track=1),
    )
    second = idx.upsert(
        file_path,
        mtime_ns=77,
        size=456,
        tags=TagData(),
        content_sha1="beefcafe",
    )
    idx.close()

    assert second.track_uid == "sha1:beefcafe"
    assert second.strict_identity_key == first.strict_identity_key


def test_concurrent_upsert_and_get(tmp_path):
    """Stress-test TrackIdentityIndex with concurrent writers and readers."""
    import threading

    db_path = tmp_path / "concurrent_identity.db"
    idx = TrackIdentityIndex(db_path)
    idx.open()

    errors: list[str] = []

    def worker(pid: int) -> None:
        try:
            for i in range(10):
                path = tmp_path / f"artist_{pid}" / f"album_{i}" / f"track_{i}.mp3"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x")
                rec = idx.upsert(
                    path,
                    mtime_ns=pid * 1000 + i,
                    size=i * 100,
                    tags=TagData(title=f"Song-{pid}-{i}", artist="Artist", album="Album", track=i + 1),
                )
                fetched = idx.get(path, pid * 1000 + i, i * 100)
                if fetched is not None and rec is not None:
                    assert fetched.track_uid == rec.track_uid
        except Exception as e:
            errors.append(f"worker {pid}: {e}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    idx.close()
    assert not errors, f"Concurrent errors: {errors}"


def test_double_close_is_safe(tmp_path):
    db_path = tmp_path / "safe.db"
    idx = TrackIdentityIndex(db_path)
    idx.open()
    idx.close()
    idx.close()


def test_get_before_open_raises(tmp_path):
    idx = TrackIdentityIndex(tmp_path / "never.db")
    with pytest.raises(RuntimeError, match="not open"):
        idx.get(tmp_path / "f.mp3", 1, 1)


def test_open_cleans_up_on_schema_failure(tmp_path):
    """Verify a failed open() doesn't leak connection (C2 regression test)."""
    db_path = tmp_path / "corrupt.db"
    idx = TrackIdentityIndex(db_path)
    idx._db_path = tmp_path  # type: ignore[assignment]
    with pytest.raises(Exception):
        idx.open()
    idx._db_path = db_path
    idx.open()
    idx.close()
