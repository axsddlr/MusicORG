"""Tests for musicorg.core.library_db."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from musicorg.core.library_db import (
    LibraryDatabase,
    TrackRecord,
)


@pytest.fixture
def db(tmp_path: Path) -> LibraryDatabase:
    lib = LibraryDatabase(tmp_path / "library.db")
    lib.open()
    yield lib
    lib.close()


class TestArtistOperations:
    def test_get_or_create_artist_returns_id(self, db: LibraryDatabase) -> None:
        artist_id = db.get_or_create_artist("Test Artist")
        assert isinstance(artist_id, int)
        assert artist_id > 0

    def test_get_or_create_artist_is_idempotent(self, db: LibraryDatabase) -> None:
        first = db.get_or_create_artist("Unique Artist")
        second = db.get_or_create_artist("Unique Artist")
        assert first == second

    def test_get_artist(self, db: LibraryDatabase) -> None:
        artist_id = db.get_or_create_artist("Some Artist")
        record = db.get_artist(artist_id)
        assert record is not None
        assert record.name == "Some Artist"

    def test_get_artist_nonexistent(self, db: LibraryDatabase) -> None:
        assert db.get_artist(99999) is None

    def test_list_artists(self, db: LibraryDatabase) -> None:
        db.get_or_create_artist("Beta")
        db.get_or_create_artist("Alpha")
        artists = db.list_artists()
        assert len(artists) >= 2
        assert artists[0].name == "Alpha"

    def test_search_artists(self, db: LibraryDatabase) -> None:
        db.get_or_create_artist("Electric Light Orchestra")
        db.get_or_create_artist("Nirvana")
        results = db.search_artists("electric")
        assert len(results) == 1
        assert results[0].name == "Electric Light Orchestra"

    def test_default_unknown_artist(self, db: LibraryDatabase) -> None:
        artist_id = db.get_or_create_artist("")
        record = db.get_artist(artist_id)
        assert record is not None
        assert record.name == "Unknown Artist"


class TestAlbumOperations:
    def test_get_or_create_album(self, db: LibraryDatabase) -> None:
        artist_id = db.get_or_create_artist("Artist")
        album_id = db.get_or_create_album(artist_id, "Album Title", year=2024, genre="Rock")
        assert isinstance(album_id, int)
        assert album_id > 0

    def test_get_or_create_album_is_idempotent(self, db: LibraryDatabase) -> None:
        artist_id = db.get_or_create_artist("Artist")
        first = db.get_or_create_album(artist_id, "Same Album")
        second = db.get_or_create_album(artist_id, "Same Album")
        assert first == second

    def test_get_album(self, db: LibraryDatabase) -> None:
        artist_id = db.get_or_create_artist("Artist")
        album_id = db.get_or_create_album(artist_id, "Album", year=2000, genre="Jazz")
        record = db.get_album(album_id)
        assert record is not None
        assert record.title == "Album"
        assert record.year == 2000
        assert record.genre == "Jazz"

    def test_get_albums_by_artist(self, db: LibraryDatabase) -> None:
        artist_id = db.get_or_create_artist("Artist")
        db.get_or_create_album(artist_id, "First", year=1990)
        db.get_or_create_album(artist_id, "Second", year=2000)
        albums = db.get_albums_by_artist(artist_id)
        assert len(albums) == 2
        assert albums[0].title == "First"

    def test_search_albums(self, db: LibraryDatabase) -> None:
        artist_id = db.get_or_create_artist("Artist")
        db.get_or_create_album(artist_id, "Greatest Hits")
        db.get_or_create_album(artist_id, "Other Album")
        results = db.search_albums("greatest")
        assert len(results) >= 1

    def test_default_unknown_album(self, db: LibraryDatabase) -> None:
        artist_id = db.get_or_create_artist("Artist")
        album_id = db.get_or_create_album(artist_id, "")
        record = db.get_album(album_id)
        assert record is not None
        assert record.title == "Unknown Album"


class TestTrackOperations:
    def test_upsert_track(self, db: LibraryDatabase) -> None:
        record = db.upsert_track(
            path="/music/song.mp3",
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            track_number=1,
            duration=180.5,
            bitrate=320,
            file_size=1024,
            mtime_ns=123456789,
        )
        assert isinstance(record.track_id, int)
        assert record.title == "Test Song"
        assert record.artist == "Test Artist"
        assert record.format == "mp3"

    def test_upsert_track_is_idempotent(self, db: LibraryDatabase) -> None:
        first = db.upsert_track(path="/music/song.mp3", title="Song", artist="A", album="B")
        second = db.upsert_track(path="/music/song.mp3", title="Song", artist="A", album="B")
        assert first.track_id == second.track_id

    def test_upsert_updates_existing(self, db: LibraryDatabase) -> None:
        db.upsert_track(path="/music/song.mp3", title="Old", artist="A", album="B")
        updated = db.upsert_track(
            path="/music/song.mp3", title="New Title", artist="A", album="B", year=2024,
        )
        assert updated.title == "New Title"
        fetched = db.get_track("/music/song.mp3")
        assert fetched is not None
        assert fetched.title == "New Title"

    def test_get_track(self, db: LibraryDatabase) -> None:
        db.upsert_track(path="/music/song.mp3", title="Song", artist="A", album="B")
        record = db.get_track("/music/song.mp3")
        assert record is not None
        assert record.title == "Song"

    def test_get_track_nonexistent(self, db: LibraryDatabase) -> None:
        assert db.get_track("/nonexistent.mp3") is None

    def test_get_tracks_by_album(self, db: LibraryDatabase) -> None:
        db.upsert_track(path="/music/one.mp3", title="One", artist="A", album="Album", track_number=1)
        db.upsert_track(path="/music/two.mp3", title="Two", artist="A", album="Album", track_number=2)
        album = db.search_albums("Album")[0]
        tracks = db.get_tracks_by_album(album.album_id)
        assert len(tracks) == 2
        assert tracks[0].track_number == 1

    def test_remove_track(self, db: LibraryDatabase) -> None:
        db.upsert_track(path="/music/song.mp3", title="Song", artist="A", album="B")
        assert db.get_track("/music/song.mp3") is not None
        db.remove_track("/music/song.mp3")
        assert db.get_track("/music/song.mp3") is None

    def test_remove_missing_tracks(self, db: LibraryDatabase) -> None:
        from musicorg.core.library_db import _normalize_path
        path_a = str(Path("/music/a.mp3").resolve())
        path_b = str(Path("/music/b.mp3").resolve())
        db.upsert_track(path=path_a, title="A", artist="X", album="Y")
        db.upsert_track(path=path_b, title="B", artist="X", album="Y")
        removed = db.remove_missing_tracks({path_a})
        assert len(removed) == 1
        assert path_b in removed
        assert db.get_track(path_a) is not None
        assert db.get_track(path_b) is None


class TestSearch:
    def test_search_tracks_by_title(self, db: LibraryDatabase) -> None:
        db.upsert_track(path="/m/song.mp3", title="Wonderwall", artist="Oasis", album="DM")
        results = db.search_tracks("wonderwall")
        assert len(results) == 1

    def test_search_tracks_by_artist(self, db: LibraryDatabase) -> None:
        db.upsert_track(path="/m/s.mp3", title="Song", artist="Nirvana", album="Nevermind")
        results = db.search_tracks("nirvana")
        assert len(results) >= 1

    def test_search_tracks_by_album(self, db: LibraryDatabase) -> None:
        db.upsert_track(path="/m/s.mp3", title="Song", artist="A", album="The Wall")
        results = db.search_tracks("the wall")
        assert len(results) == 1

    def test_search_with_artist_filter(self, db: LibraryDatabase) -> None:
        db.upsert_track(path="/m/1.mp3", title="Song", artist="Beatles", album="Help")
        db.upsert_track(path="/m/2.mp3", title="Song", artist="Stones", album="Help")
        results = db.search_tracks("song", artist_filter="beatles")
        assert len(results) == 1

    def test_search_with_year_range(self, db: LibraryDatabase) -> None:
        db.upsert_track(path="/m/1.mp3", title="Song", artist="A", album="Old", year=1980)
        db.upsert_track(path="/m/2.mp3", title="Song", artist="A", album="New", year=2000)
        results = db.search_tracks("", year_min=1990)
        assert len(results) == 1

    def test_search_no_results(self, db: LibraryDatabase) -> None:
        results = db.search_tracks("zzz_nonexistent_zzz")
        assert len(results) == 0


class TestArtwork:
    def test_artwork_dedup(self, db: LibraryDatabase) -> None:
        data = b"fake_artwork_bytes_123"
        track1 = db.upsert_track(
            path="/m/a.mp3", title="A", artist="X", album="Y",
            artwork_data=data, artwork_mime="image/jpeg",
        )
        track2 = db.upsert_track(
            path="/m/b.mp3", title="B", artist="X", album="Y",
            artwork_data=data, artwork_mime="image/jpeg",
        )
        assert track1.artwork_id == track2.artwork_id

    def test_get_artwork(self, db: LibraryDatabase) -> None:
        data = b"artwork_data_xyz"
        db.upsert_track(
            path="/m/s.mp3", title="S", artist="A", album="B",
            artwork_data=data, artwork_mime="image/png",
        )
        track = db.get_track("/m/s.mp3")
        assert track is not None and track.artwork_id is not None
        result = db.get_artwork_with_mime(track.artwork_id)
        assert result is not None
        assert result[0] == data
        assert "png" in result[1]

    def test_artwork_none(self, db: LibraryDatabase) -> None:
        track = db.upsert_track(path="/m/s.mp3", title="S", artist="A", album="B")
        assert track.artwork_id is None


class TestBatch:
    def test_batch_transaction(self, db: LibraryDatabase) -> None:
        db.begin_batch()
        db.upsert_track(path="/m/1.mp3", title="One", artist="A", album="B")
        db.upsert_track(path="/m/2.mp3", title="Two", artist="A", album="B")
        db.end_batch()
        assert db.total_tracks() == 2

    def test_nested_batch(self, db: LibraryDatabase) -> None:
        db.begin_batch()
        db.begin_batch()
        db.upsert_track(path="/m/1.mp3", title="One", artist="A", album="B")
        db.end_batch()
        assert db.total_tracks() == 1
        db.end_batch()


class TestStats:
    def test_total_tracks(self, db: LibraryDatabase) -> None:
        assert db.total_tracks() == 0
        db.upsert_track(path="/m/a.mp3", title="A", artist="X", album="Y")
        assert db.total_tracks() == 1

    def test_total_albums(self, db: LibraryDatabase) -> None:
        assert db.total_albums() == 0
        db.upsert_track(path="/m/a.mp3", title="A", artist="X", album="Y")
        assert db.total_albums() == 1

    def test_total_artists(self, db: LibraryDatabase) -> None:
        assert db.total_artists() == 0
        db.upsert_track(path="/m/a.mp3", title="A", artist="X", album="Y")
        assert db.total_artists() == 1

    def test_total_duration(self, db: LibraryDatabase) -> None:
        db.upsert_track(path="/m/a.mp3", title="A", artist="X", album="Y", duration=100.0)
        db.upsert_track(path="/m/b.mp3", title="B", artist="X", album="Y", duration=200.0)
        assert db.total_duration() == 300.0

    def test_total_size(self, db: LibraryDatabase) -> None:
        db.upsert_track(path="/m/a.mp3", title="A", artist="X", album="Y", file_size=500)
        db.upsert_track(path="/m/b.mp3", title="B", artist="X", album="Y", file_size=1500)
        assert db.total_size() == 2000

    def test_recently_added(self, db: LibraryDatabase) -> None:
        db.upsert_track(path="/m/a.mp3", title="A", artist="X", album="Y")
        recent = db.recently_added(limit=10)
        assert len(recent) == 1


class TestLifecycle:
    def test_double_open_is_safe(self, tmp_path: Path) -> None:
        lib = LibraryDatabase(tmp_path / "safe.db")
        lib.open()
        lib.open()
        lib.close()

    def test_double_close_is_safe(self, tmp_path: Path) -> None:
        lib = LibraryDatabase(tmp_path / "safe.db")
        lib.open()
        lib.close()
        lib.close()

    def test_get_before_open_raises(self, tmp_path: Path) -> None:
        lib = LibraryDatabase(tmp_path / "never.db")
        with pytest.raises(RuntimeError, match="not open"):
            lib.get_track("/f.mp3")

    def test_reopen_after_close(self, tmp_path: Path) -> None:
        path = tmp_path / "reopen.db"
        lib = LibraryDatabase(path)
        lib.open()
        lib.upsert_track(path="/m/s.mp3", title="T", artist="A", album="B")
        lib.close()
        lib2 = LibraryDatabase(path)
        lib2.open()
        assert lib2.total_tracks() == 1
        lib2.close()


class TestConcurrency:
    def test_concurrent_upsert(self, tmp_path: Path) -> None:
        lib = LibraryDatabase(tmp_path / "concurrent.db")
        lib.open()
        errors: list[str] = []

        def worker(wid: int) -> None:
            try:
                for i in range(20):
                    lib.upsert_track(
                        path=f"/m/w{wid}_t{i}.mp3",
                        title=f"Song-{wid}-{i}",
                        artist="Artist",
                        album="Album",
                    )
            except Exception as e:
                errors.append(f"worker {wid}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent errors: {errors}"
        assert lib.total_tracks() == 80
        lib.close()
