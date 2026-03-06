"""Tests for persistent track identity index."""

from pathlib import Path

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
