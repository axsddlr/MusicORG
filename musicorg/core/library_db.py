"""Persistent normalized library database for musicorg.

Replaces tag_cache.db + track_identity.db + in-memory _library_index
with a single SQLite database using a normalized artists/albums/tracks schema.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

_AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".m4a", ".ogg", ".opus",
    ".wav", ".aiff", ".wv", ".ape", ".tak",
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS artists (
    artist_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    name_normalized TEXT NOT NULL,
    sort_name       TEXT NOT NULL DEFAULT '',
    thumbnail       BLOB,
    UNIQUE(name)
);

CREATE TABLE IF NOT EXISTS albums (
    album_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_id         INTEGER NOT NULL REFERENCES artists(artist_id),
    title             TEXT NOT NULL,
    title_normalized  TEXT NOT NULL,
    year              INTEGER DEFAULT 0,
    genre             TEXT DEFAULT '',
    track_count       INTEGER DEFAULT 0,
    disc_count        INTEGER DEFAULT 1,
    date_added        INTEGER NOT NULL DEFAULT (unixepoch()),
    date_modified     INTEGER NOT NULL DEFAULT (unixepoch()),
    UNIQUE(artist_id, title)
);

CREATE TABLE IF NOT EXISTS tracks (
    track_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id          INTEGER NOT NULL REFERENCES albums(album_id),
    path              TEXT NOT NULL UNIQUE,
    title             TEXT NOT NULL DEFAULT '',
    artist            TEXT NOT NULL DEFAULT '',
    track_number      INTEGER DEFAULT 0,
    disc_number       INTEGER DEFAULT 1,
    duration          REAL DEFAULT 0.0,
    bitrate           INTEGER DEFAULT 0,
    format            TEXT NOT NULL,
    file_size         INTEGER NOT NULL DEFAULT 0,
    mtime_ns          INTEGER NOT NULL DEFAULT 0,
    content_sha1      TEXT NOT NULL DEFAULT '',
    rating            INTEGER DEFAULT 0,
    play_count        INTEGER DEFAULT 0,
    skip_count        INTEGER DEFAULT 0,
    last_played       INTEGER DEFAULT 0,
    custom_tags       TEXT NOT NULL DEFAULT '{}',
    date_added        INTEGER NOT NULL DEFAULT (unixepoch()),
    date_modified     INTEGER NOT NULL DEFAULT (unixepoch()),
    artwork_id        INTEGER REFERENCES artwork(artwork_id)
);

CREATE TABLE IF NOT EXISTS artwork (
    artwork_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256      TEXT NOT NULL UNIQUE,
    data        BLOB NOT NULL,
    mime        TEXT NOT NULL DEFAULT 'image/jpeg',
    width       INTEGER DEFAULT 0,
    height      INTEGER DEFAULT 0,
    refcount    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tracks_album_id ON tracks(album_id);
CREATE INDEX IF NOT EXISTS idx_tracks_path ON tracks(path);
CREATE INDEX IF NOT EXISTS idx_tracks_sha1 ON tracks(content_sha1);
CREATE INDEX IF NOT EXISTS idx_albums_artist_id ON albums(artist_id);
CREATE INDEX IF NOT EXISTS idx_artwork_sha256 ON artwork(sha256);

CREATE TABLE IF NOT EXISTS playlists (
    playlist_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    is_smart    INTEGER NOT NULL DEFAULT 0,
    rule_json   TEXT NOT NULL DEFAULT '',
    created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL REFERENCES playlists(playlist_id) ON DELETE CASCADE,
    track_path  TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (playlist_id, track_path)
);
"""


@dataclass
class ArtistRecord:
    artist_id: int
    name: str
    sort_name: str
    thumbnail: bytes | None


@dataclass
class AlbumRecord:
    album_id: int
    artist_id: int
    title: str
    year: int
    genre: str
    track_count: int
    disc_count: int
    date_added: int
    date_modified: int


@dataclass
class TrackRecord:
    track_id: int
    album_id: int
    path: str
    title: str
    artist: str
    track_number: int
    disc_number: int
    duration: float
    bitrate: int
    format: str
    file_size: int
    mtime_ns: int
    content_sha1: str
    rating: int
    play_count: int
    date_added: int
    date_modified: int
    artwork_id: int | None


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def _normalize_path(path: str | Path) -> str:
    try:
        return str(Path(path).resolve())
    except Exception:
        return str(Path(path))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LibraryDatabase:
    """Persistent normalized library with artists, albums, tracks and artwork.

    Thread-safe for concurrent reads and serialized writes using RLock.
    Uses WAL mode for concurrent reads.
    """

    SCHEMA_VERSION = "1"

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._batch_depth = 0

    # -- lifecycle --

    def open(self) -> None:
        if self._conn is not None:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.executescript(SCHEMA_SQL)
        self._migrate(conn)
        conn.execute(
            "INSERT OR IGNORE INTO metadata (key, value) VALUES (?, ?)",
            ("schema_version", self.SCHEMA_VERSION),
        )
        conn.commit()
        self._conn = conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        for col_def in ("custom_tags TEXT NOT NULL DEFAULT '{}'",):
            try:
                conn.execute(f"ALTER TABLE tracks ADD COLUMN {col_def}")
            except sqlite3.OperationalError:
                pass
        for table_sql in (
            "CREATE TABLE IF NOT EXISTS playlists (playlist_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, is_smart INTEGER NOT NULL DEFAULT 0, rule_json TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL DEFAULT (unixepoch()), updated_at INTEGER NOT NULL DEFAULT (unixepoch()))",
            "CREATE TABLE IF NOT EXISTS playlist_tracks (playlist_id INTEGER NOT NULL REFERENCES playlists(playlist_id) ON DELETE CASCADE, track_path TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (playlist_id, track_path))",
        ):
            try:
                conn.execute(table_sql)
            except sqlite3.OperationalError:
                pass

    def close(self) -> None:
        if self._conn is None:
            return
        self._conn.close()
        self._conn = None

    # -- transactions --

    def begin_batch(self) -> None:
        self._batch_depth += 1
        if self._batch_depth == 1:
            self._conn_or_raise().execute("BEGIN")

    def end_batch(self) -> None:
        if self._batch_depth <= 0:
            return
        self._batch_depth -= 1
        if self._batch_depth == 0:
            self._conn_or_raise().execute("COMMIT")

    # -- artists --

    def get_or_create_artist(self, name: str) -> int:
        name = name.strip() or "Unknown Artist"
        normalized = _normalize(name)
        conn = self._conn_or_raise()
        row = conn.execute(
            "SELECT artist_id FROM artists WHERE name = ?", (name,)
        ).fetchone()
        if row is not None:
            return int(row[0])
        with self._lock:
            conn.execute(
                "INSERT OR IGNORE INTO artists (name, name_normalized) VALUES (?, ?)",
                (name, normalized),
            )
            if self._batch_depth == 0:
                conn.commit()
            return int(
                conn.execute(
                    "SELECT artist_id FROM artists WHERE name = ?", (name,)
                ).fetchone()[0]
            )

    def get_artist(self, artist_id: int) -> ArtistRecord | None:
        row = self._conn_or_raise().execute(
            "SELECT artist_id, name, sort_name, thumbnail FROM artists WHERE artist_id = ?",
            (artist_id,),
        ).fetchone()
        if row is None:
            return None
        return ArtistRecord(
            artist_id=int(row[0]),
            name=str(row[1]),
            sort_name=str(row[2] or ""),
            thumbnail=bytes(row[3]) if row[3] is not None else None,
        )

    def search_artists(self, query: str) -> list[ArtistRecord]:
        pattern = f"%{_normalize(query)}%"
        rows = self._conn_or_raise().execute(
            "SELECT artist_id, name, sort_name, thumbnail FROM artists WHERE name_normalized LIKE ? ORDER BY name",
            (pattern,),
        ).fetchall()
        return [
            ArtistRecord(
                artist_id=int(r[0]), name=str(r[1]),
                sort_name=str(r[2] or ""),
                thumbnail=bytes(r[3]) if r[3] is not None else None,
            )
            for r in rows
        ]

    def list_artists(self) -> list[ArtistRecord]:
        rows = self._conn_or_raise().execute(
            "SELECT artist_id, name, sort_name, thumbnail FROM artists ORDER BY name"
        ).fetchall()
        return [
            ArtistRecord(
                artist_id=int(r[0]), name=str(r[1]),
                sort_name=str(r[2] or ""),
                thumbnail=bytes(r[3]) if r[3] is not None else None,
            )
            for r in rows
        ]

    # -- albums --

    def get_or_create_album(
        self, artist_id: int, title: str,
        year: int = 0, genre: str = "",
    ) -> int:
        title = title.strip() or "Unknown Album"
        normalized = _normalize(title)
        now = int(time.time())
        conn = self._conn_or_raise()
        row = conn.execute(
            "SELECT album_id FROM albums WHERE artist_id = ? AND title = ?",
            (artist_id, title),
        ).fetchone()
        if row is not None:
            album_id = int(row[0])
            if year or genre:
                updates: list[str] = []
                params: list[Any] = []
                if year:
                    updates.append("year = ?")
                    params.append(year)
                if genre:
                    updates.append("genre = ?")
                    params.append(genre)
                updates.append("date_modified = ?")
                params.append(now)
                params.append(album_id)
                with self._lock:
                    conn.execute(
                        f"UPDATE albums SET {', '.join(updates)} WHERE album_id = ?",
                        params,
                    )
                    if self._batch_depth == 0:
                        conn.commit()
            return album_id
        with self._lock:
            conn.execute(
                """INSERT OR IGNORE INTO albums
                   (artist_id, title, title_normalized, year, genre)
                   VALUES (?, ?, ?, ?, ?)""",
                (artist_id, title, normalized, year, genre),
            )
            if self._batch_depth == 0:
                conn.commit()
            return int(
                conn.execute(
                    "SELECT album_id FROM albums WHERE artist_id = ? AND title = ?",
                    (artist_id, title),
                ).fetchone()[0]
            )

    def get_album(self, album_id: int) -> AlbumRecord | None:
        row = self._conn_or_raise().execute(
            """SELECT album_id, artist_id, title, year, genre,
                      track_count, disc_count, date_added, date_modified
               FROM albums WHERE album_id = ?""",
            (album_id,),
        ).fetchone()
        if row is None:
            return None
        return AlbumRecord(
            album_id=int(row[0]), artist_id=int(row[1]),
            title=str(row[2]), year=int(row[3] or 0),
            genre=str(row[4] or ""),
            track_count=int(row[5] or 0),
            disc_count=int(row[6] or 1),
            date_added=int(row[7] or 0),
            date_modified=int(row[8] or 0),
        )

    def get_albums_by_artist(self, artist_id: int) -> list[AlbumRecord]:
        rows = self._conn_or_raise().execute(
            """SELECT album_id, artist_id, title, year, genre,
                      track_count, disc_count, date_added, date_modified
               FROM albums WHERE artist_id = ? ORDER BY year, title""",
            (artist_id,),
        ).fetchall()
        return [
            AlbumRecord(
                album_id=int(r[0]), artist_id=int(r[1]),
                title=str(r[2]), year=int(r[3] or 0),
                genre=str(r[4] or ""),
                track_count=int(r[5] or 0),
                disc_count=int(r[6] or 1),
                date_added=int(r[7] or 0),
                date_modified=int(r[8] or 0),
            )
            for r in rows
        ]

    def search_albums(self, query: str) -> list[AlbumRecord]:
        pattern = f"%{_normalize(query)}%"
        rows = self._conn_or_raise().execute(
            """SELECT a.album_id, a.artist_id, a.title, a.year, a.genre,
                      a.track_count, a.disc_count, a.date_added, a.date_modified
               FROM albums a WHERE a.title_normalized LIKE ?
               ORDER BY a.year, a.title""",
            (pattern,),
        ).fetchall()
        return [
            AlbumRecord(
                album_id=int(r[0]), artist_id=int(r[1]),
                title=str(r[2]), year=int(r[3] or 0),
                genre=str(r[4] or ""),
                track_count=int(r[5] or 0),
                disc_count=int(r[6] or 1),
                date_added=int(r[7] or 0),
                date_modified=int(r[8] or 0),
            )
            for r in rows
        ]

    def list_albums(self) -> list[AlbumRecord]:
        rows = self._conn_or_raise().execute(
            """SELECT album_id, artist_id, title, year, genre,
                      track_count, disc_count, date_added, date_modified
               FROM albums ORDER BY year, title"""
        ).fetchall()
        return [
            AlbumRecord(
                album_id=int(r[0]), artist_id=int(r[1]),
                title=str(r[2]), year=int(r[3] or 0),
                genre=str(r[4] or ""),
                track_count=int(r[5] or 0),
                disc_count=int(r[6] or 1),
                date_added=int(r[7] or 0),
                date_modified=int(r[8] or 0),
            )
            for r in rows
        ]

    # -- tracks --

    def upsert_track(
        self,
        path: str | Path,
        title: str = "",
        artist: str = "",
        album: str = "",
        albumartist: str = "",
        track_number: int = 0,
        disc_number: int = 1,
        year: int = 0,
        genre: str = "",
        duration: float = 0.0,
        bitrate: int = 0,
        file_size: int = 0,
        mtime_ns: int = 0,
        content_sha1: str = "",
        artwork_data: bytes | None = None,
        artwork_mime: str = "",
    ) -> TrackRecord:
        normalized_path = _normalize_path(path)
        fmt = Path(normalized_path).suffix.lower().lstrip(".") or "unknown"
        art_artist = albumartist or artist
        art_name = art_artist or "Unknown Artist"
        art_album = album or "Unknown Album"

        artist_id = self.get_or_create_artist(art_name)
        album_id = self.get_or_create_album(artist_id, art_album, year=year, genre=genre)

        artwork_id: int | None = None
        if artwork_data:
            artwork_id = self._store_artwork(artwork_data, artwork_mime)

        now = int(time.time())
        conn = self._conn_or_raise()
        with self._lock:
            conn.execute(
                """INSERT INTO tracks (
                    album_id, path, title, artist, track_number,
                    disc_number, duration, bitrate, format,
                    file_size, mtime_ns, content_sha1,
                    date_added, date_modified, artwork_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    album_id = excluded.album_id,
                    title = excluded.title,
                    artist = excluded.artist,
                    track_number = excluded.track_number,
                    disc_number = excluded.disc_number,
                    duration = excluded.duration,
                    bitrate = excluded.bitrate,
                    format = excluded.format,
                    file_size = excluded.file_size,
                    mtime_ns = excluded.mtime_ns,
                    content_sha1 = excluded.content_sha1,
                    date_modified = excluded.date_modified,
                    artwork_id = COALESCE(excluded.artwork_id, tracks.artwork_id)
                """,
                (
                    album_id, normalized_path, title, artist, track_number,
                    disc_number, duration, bitrate, fmt,
                    file_size, mtime_ns, content_sha1,
                    now, now, artwork_id,
                ),
            )
            if self._batch_depth == 0:
                conn.commit()

        row = conn.execute(
            "SELECT track_id, date_added FROM tracks WHERE path = ?",
            (normalized_path,),
        ).fetchone()
        track_id = int(row[0])
        date_added = int(row[1] or now)

        self._update_album_track_count(album_id)

        return TrackRecord(
            track_id=track_id, album_id=album_id,
            path=normalized_path, title=title, artist=artist,
            track_number=track_number, disc_number=disc_number,
            duration=duration, bitrate=bitrate, format=fmt,
            file_size=file_size, mtime_ns=mtime_ns,
            content_sha1=content_sha1,
            rating=0, play_count=0,
            date_added=date_added, date_modified=now,
            artwork_id=artwork_id,
        )

    def get_track(self, path: str | Path) -> TrackRecord | None:
        row = self._conn_or_raise().execute(
            """SELECT track_id, album_id, path, title, artist,
                      track_number, disc_number, duration, bitrate, format,
                      file_size, mtime_ns, content_sha1,
                      rating, play_count,
                      date_added, date_modified, artwork_id
               FROM tracks WHERE path = ?""",
            (_normalize_path(path),),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_track(row)

    def get_tracks_by_album(self, album_id: int) -> list[TrackRecord]:
        rows = self._conn_or_raise().execute(
            """SELECT track_id, album_id, path, title, artist,
                      track_number, disc_number, duration, bitrate, format,
                      file_size, mtime_ns, content_sha1,
                      rating, play_count,
                      date_added, date_modified, artwork_id
               FROM tracks WHERE album_id = ?
               ORDER BY disc_number, track_number, path""",
            (album_id,),
        ).fetchall()
        return [self._row_to_track(r) for r in rows]

    def search_tracks(
        self,
        query: str,
        artist_filter: str | None = None,
        genre_filter: str | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
    ) -> list[TrackRecord]:
        sql = """SELECT t.track_id, t.album_id, t.path, t.title, t.artist,
                        t.track_number, t.disc_number, t.duration, t.bitrate, t.format,
                        t.file_size, t.mtime_ns, t.content_sha1,
                        t.rating, t.play_count,
                        t.date_added, t.date_modified, t.artwork_id
                 FROM tracks t
                 JOIN albums a ON t.album_id = a.album_id
                 JOIN artists ar ON a.artist_id = ar.artist_id
                 WHERE 1=1"""
        params: list[Any] = []

        if query:
            pattern = f"%{_normalize(query)}%"
            sql += """ AND (ar.name_normalized LIKE ?
                          OR a.title_normalized LIKE ?
                          OR t.title LIKE ?)"""
            params.extend([pattern, pattern, pattern])
        if artist_filter:
            sql += " AND ar.name_normalized LIKE ?"
            params.append(f"%{_normalize(artist_filter)}%")
        if genre_filter:
            sql += " AND a.genre LIKE ?"
            params.append(f"%{genre_filter}%")
        if year_min is not None:
            sql += " AND a.year >= ?"
            params.append(year_min)
        if year_max is not None:
            sql += " AND a.year <= ?"
            params.append(year_max)

        sql += " ORDER BY ar.name, a.year, a.title, t.disc_number, t.track_number"
        rows = self._conn_or_raise().execute(sql, params).fetchall()
        return [self._row_to_track(r) for r in rows]

    def get_track_tags(self, path: str | Path) -> dict[str, Any] | None:
        """Return a dict of all tag fields for a track (denormalized with album/artist)."""
        row = self._conn_or_raise().execute(
            """SELECT t.title, t.artist, a.title, ar.name,
                      t.track_number, t.disc_number, a.year, a.genre,
                      t.duration, t.bitrate, t.artwork_id,
                      t.file_size, t.mtime_ns
               FROM tracks t
               JOIN albums a ON t.album_id = a.album_id
               JOIN artists ar ON a.artist_id = ar.artist_id
               WHERE t.path = ?""",
            (_normalize_path(path),),
        ).fetchone()
        if row is None:
            return None

        artwork: tuple[bytes, str] | None = None
        if row[10] is not None:
            aw = self.get_artwork_with_mime(int(row[10]))
            if aw is not None:
                artwork = aw

        return {
            "title": str(row[0] or ""),
            "artist": str(row[1] or ""),
            "album": str(row[2] or ""),
            "albumartist": str(row[3] or ""),
            "track": int(row[4] or 0),
            "disc": int(row[5] or 1),
            "year": int(row[6] or 0),
            "genre": str(row[7] or ""),
            "duration": float(row[8] or 0.0),
            "bitrate": int(row[9] or 0),
            "artwork_data": artwork[0] if artwork else None,
            "artwork_mime": artwork[1] if artwork else "",
        }

    def remove_track(self, path: str | Path) -> None:
        normalized = _normalize_path(path)
        conn = self._conn_or_raise()
        row = conn.execute(
            "SELECT album_id FROM tracks WHERE path = ?", (normalized,)
        ).fetchone()
        with self._lock:
            conn.execute("DELETE FROM tracks WHERE path = ?", (normalized,))
            if self._batch_depth == 0:
                conn.commit()
        if row is not None:
            self._update_album_track_count(int(row[0]))

    def remove_missing_tracks(self, known_paths: set[str]) -> list[str]:
        conn = self._conn_or_raise()
        normalized_known = {_normalize_path(p) for p in known_paths}
        all_tracks = conn.execute("SELECT path, album_id FROM tracks").fetchall()
        removed: list[str] = []
        affected_albums: set[int] = set()
        for path, album_id in all_tracks:
            if path not in normalized_known:
                removed.append(path)
                affected_albums.add(int(album_id))
        if removed:
            with self._lock:
                placeholders = ",".join("?" for _ in removed)
                conn.execute(
                    f"DELETE FROM tracks WHERE path IN ({placeholders})", removed
                )
                if self._batch_depth == 0:
                    conn.commit()
            for album_id in affected_albums:
                self._update_album_track_count(album_id)
        return removed

    # -- artwork --

    def _store_artwork(self, data: bytes, mime: str) -> int | None:
        if not data:
            return None
        sha = _sha256(data)
        conn = self._conn_or_raise()
        row = conn.execute(
            "SELECT artwork_id, refcount FROM artwork WHERE sha256 = ?", (sha,)
        ).fetchone()
        if row is not None:
            artwork_id = int(row[0])
            with self._lock:
                conn.execute(
                    "UPDATE artwork SET refcount = refcount + 1 WHERE artwork_id = ?",
                    (artwork_id,),
                )
                if self._batch_depth == 0:
                    conn.commit()
            return artwork_id
        mime_clean = mime.strip().lower() if mime else "image/jpeg"
        if not mime_clean.startswith("image/"):
            mime_clean = "image/jpeg"
        with self._lock:
            conn.execute(
                "INSERT INTO artwork (sha256, data, mime) VALUES (?, ?, ?)",
                (sha, data, mime_clean),
            )
            if self._batch_depth == 0:
                conn.commit()
            return int(
                conn.execute(
                    "SELECT artwork_id FROM artwork WHERE sha256 = ?", (sha,)
                ).fetchone()[0]
            )

    def get_artwork(self, artwork_id: int) -> bytes | None:
        row = self._conn_or_raise().execute(
            "SELECT data FROM artwork WHERE artwork_id = ?", (artwork_id,)
        ).fetchone()
        return bytes(row[0]) if row is not None else None

    def get_artwork_with_mime(self, artwork_id: int) -> tuple[bytes, str] | None:
        row = self._conn_or_raise().execute(
            "SELECT data, mime FROM artwork WHERE artwork_id = ?", (artwork_id,)
        ).fetchone()
        if row is None:
            return None
        return (bytes(row[0]), str(row[1]))

    def get_artwork_for_track(self, path: str | Path) -> tuple[bytes, str] | None:
        row = self._conn_or_raise().execute(
            """SELECT a.data, a.mime FROM artwork a
               JOIN tracks t ON t.artwork_id = a.artwork_id
               WHERE t.path = ? LIMIT 1""",
            (_normalize_path(path),),
        ).fetchone()
        if row is None:
            return None
        return (bytes(row[0]), str(row[1]))

    def get_artwork_for_album(self, album_id: int) -> tuple[bytes, str] | None:
        row = self._conn_or_raise().execute(
            """SELECT a.data, a.mime FROM artwork a
               JOIN tracks t ON t.artwork_id = a.artwork_id
               WHERE t.album_id = ? AND a.data IS NOT NULL
               LIMIT 1""",
            (album_id,),
        ).fetchone()
        if row is None:
            return None
        return (bytes(row[0]), str(row[1]))

    # -- custom tags --

    def get_custom_tag(self, path: str | Path, key: str) -> str:
        tags = self._get_custom_tags(path)
        return tags.get(key, "")

    def set_custom_tag(self, path: str | Path, key: str, value: str) -> None:
        tags = self._get_custom_tags(path)
        if value:
            tags[key] = value
        else:
            tags.pop(key, None)
        self._set_custom_tags(path, tags)

    def list_custom_tag_keys(self) -> list[str]:
        keys: set[str] = set()
        rows = self._conn_or_raise().execute(
            "SELECT DISTINCT custom_tags FROM tracks WHERE custom_tags != '{}'"
        ).fetchall()
        for row in rows:
            try:
                import json
                keys.update(json.loads(str(row[0] or "{}")).keys())
            except Exception:
                pass
        return sorted(keys)

    def _get_custom_tags(self, path: str | Path) -> dict[str, str]:
        normalized = _normalize_path(path)
        row = self._conn_or_raise().execute(
            "SELECT custom_tags FROM tracks WHERE path = ?", (normalized,)
        ).fetchone()
        if row is None:
            return {}
        try:
            import json
            return json.loads(str(row[0] or "{}"))
        except Exception:
            return {}

    def _set_custom_tags(self, path: str | Path, tags: dict[str, str]) -> None:
        import json
        normalized = _normalize_path(path)
        encoded = json.dumps(tags)
        with self._lock:
            self._conn_or_raise().execute(
                "UPDATE tracks SET custom_tags = ?, date_modified = ? WHERE path = ?",
                (encoded, int(time.time()), normalized),
            )
            if self._batch_depth == 0:
                self._conn_or_raise().commit()

    # -- stats --

    def total_tracks(self) -> int:
        row = self._conn_or_raise().execute(
            "SELECT COUNT(*) FROM tracks"
        ).fetchone()
        return int(row[0]) if row else 0

    def total_albums(self) -> int:
        row = self._conn_or_raise().execute(
            "SELECT COUNT(*) FROM albums"
        ).fetchone()
        return int(row[0]) if row else 0

    def total_artists(self) -> int:
        row = self._conn_or_raise().execute(
            "SELECT COUNT(*) FROM artists"
        ).fetchone()
        return int(row[0]) if row else 0

    def total_duration(self) -> float:
        row = self._conn_or_raise().execute(
            "SELECT COALESCE(SUM(duration), 0.0) FROM tracks"
        ).fetchone()
        return float(row[0]) if row else 0.0

    def total_size(self) -> int:
        row = self._conn_or_raise().execute(
            "SELECT COALESCE(SUM(file_size), 0) FROM tracks"
        ).fetchone()
        return int(row[0]) if row else 0

    def recently_added(self, limit: int = 50) -> list[TrackRecord]:
        rows = self._conn_or_raise().execute(
            """SELECT track_id, album_id, path, title, artist,
                      track_number, disc_number, duration, bitrate, format,
                      file_size, mtime_ns, content_sha1,
                      rating, play_count,
                      date_added, date_modified, artwork_id
               FROM tracks ORDER BY date_added DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [self._row_to_track(r) for r in rows]

    # -- playlists --

    def create_playlist(self, name: str, *, is_smart: bool = False, rule_json: str = "") -> int:
        conn = self._conn_or_raise()
        now = int(time.time())
        with self._lock:
            conn.execute(
                "INSERT OR IGNORE INTO playlists (name, is_smart, rule_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (name, 1 if is_smart else 0, rule_json, now, now),
            )
            if self._batch_depth == 0:
                conn.commit()
            row = conn.execute("SELECT playlist_id FROM playlists WHERE name = ?", (name,)).fetchone()
            return int(row[0]) if row else -1

    def delete_playlist(self, playlist_id: int) -> None:
        with self._lock:
            self._conn_or_raise().execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))
            self._conn_or_raise().execute("DELETE FROM playlists WHERE playlist_id = ?", (playlist_id,))
            if self._batch_depth == 0:
                self._conn_or_raise().commit()

    def rename_playlist(self, playlist_id: int, new_name: str) -> None:
        with self._lock:
            self._conn_or_raise().execute(
                "UPDATE playlists SET name = ?, updated_at = ? WHERE playlist_id = ?",
                (new_name, int(time.time()), playlist_id),
            )
            if self._batch_depth == 0:
                self._conn_or_raise().commit()

    def list_playlists(self) -> list[dict[str, Any]]:
        rows = self._conn_or_raise().execute(
            "SELECT playlist_id, name, is_smart, rule_json, (SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id = p.playlist_id) FROM playlists p ORDER BY name"
        ).fetchall()
        return [
            {
                "id": int(r[0]), "name": str(r[1]),
                "is_smart": bool(r[2]), "rule": str(r[3] or ""),
                "count": int(r[4] or 0),
            }
            for r in rows
        ]

    def add_track_to_playlist(self, playlist_id: int, track_path: str) -> None:
        normalized = _normalize_path(track_path)
        with self._lock:
            max_order = self._conn_or_raise().execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM playlist_tracks WHERE playlist_id = ?",
                (playlist_id,),
            ).fetchone()[0]
            self._conn_or_raise().execute(
                "INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_path, sort_order) VALUES (?, ?, ?)",
                (playlist_id, normalized, int(max_order)),
            )
            if self._batch_depth == 0:
                self._conn_or_raise().commit()

    def remove_track_from_playlist(self, playlist_id: int, track_path: str) -> None:
        normalized = _normalize_path(track_path)
        with self._lock:
            self._conn_or_raise().execute(
                "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_path = ?",
                (playlist_id, normalized),
            )
            if self._batch_depth == 0:
                self._conn_or_raise().commit()

    def get_playlist_tracks(self, playlist_id: int) -> list[str]:
        rows = self._conn_or_raise().execute(
            "SELECT track_path FROM playlist_tracks WHERE playlist_id = ? ORDER BY sort_order",
            (playlist_id,),
        ).fetchall()
        return [str(r[0]) for r in rows]

    def get_playlist_track_records(self, playlist_id: int) -> list[TrackRecord]:
        rows = self._conn_or_raise().execute(
            """SELECT t.track_id, t.album_id, t.path, t.title, t.artist,
                      t.track_number, t.disc_number, t.duration, t.bitrate, t.format,
                      t.file_size, t.mtime_ns, t.content_sha1,
                      t.rating, t.play_count,
                      t.date_added, t.date_modified, t.artwork_id
               FROM tracks t
               JOIN playlist_tracks pt ON t.path = pt.track_path
               WHERE pt.playlist_id = ?
               ORDER BY pt.sort_order""",
            (playlist_id,),
        ).fetchall()
        return [self._row_to_track(r) for r in rows]

    def clear_playlist(self, playlist_id: int) -> None:
        with self._lock:
            self._conn_or_raise().execute(
                "DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,)
            )
            if self._batch_depth == 0:
                self._conn_or_raise().commit()

    # -- helpers --

    def _update_album_track_count(self, album_id: int) -> None:
        conn = self._conn_or_raise()
        row = conn.execute(
            """SELECT COUNT(*), COALESCE(MAX(disc_number), 1)
               FROM tracks WHERE album_id = ?""",
            (album_id,),
        ).fetchone()
        count = int(row[0])
        discs = int(row[1]) if row[1] is not None else 1
        with self._lock:
            conn.execute(
                "UPDATE albums SET track_count = ?, disc_count = ?, date_modified = ? WHERE album_id = ?",
                (count, discs, int(time.time()), album_id),
            )
            if self._batch_depth == 0:
                conn.commit()

    def _conn_or_raise(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("LibraryDatabase is not open")
        return self._conn

    @staticmethod
    def _row_to_track(row: sqlite3.Row | tuple) -> TrackRecord:
        return TrackRecord(
            track_id=int(row[0]), album_id=int(row[1]),
            path=str(row[2]), title=str(row[3] or ""),
            artist=str(row[4] or ""),
            track_number=int(row[5] or 0),
            disc_number=int(row[6] or 1),
            duration=float(row[7] or 0.0),
            bitrate=int(row[8] or 0),
            format=str(row[9] or ""),
            file_size=int(row[10] or 0),
            mtime_ns=int(row[11] or 0),
            content_sha1=str(row[12] or ""),
            rating=int(row[13] or 0),
            play_count=int(row[14] or 0),
            date_added=int(row[15] or 0),
            date_modified=int(row[16] or 0),
            artwork_id=int(row[17]) if row[17] is not None else None,
        )

    def _normalize_path(self, path: str | Path) -> str:
        return _normalize_path(path)
