"""SQLite-backed cache for file tag reads."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from musicorg.core.tagger import TagData

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tag_cache (
    path         TEXT    PRIMARY KEY,
    mtime_ns     INTEGER NOT NULL,
    size         INTEGER NOT NULL,
    title        TEXT    NOT NULL DEFAULT '',
    artist       TEXT    NOT NULL DEFAULT '',
    album        TEXT    NOT NULL DEFAULT '',
    albumartist  TEXT    NOT NULL DEFAULT '',
    track        INTEGER NOT NULL DEFAULT 0,
    disc         INTEGER NOT NULL DEFAULT 0,
    year         INTEGER NOT NULL DEFAULT 0,
    genre        TEXT    NOT NULL DEFAULT '',
    composer     TEXT    NOT NULL DEFAULT '',
    duration     REAL    NOT NULL DEFAULT 0.0,
    bitrate      INTEGER NOT NULL DEFAULT 0,
    artwork_data BLOB,
    artwork_mime TEXT    NOT NULL DEFAULT ''
);
"""


class TagCache:
    """Caches TagData per file path and file fingerprint."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        """Open the cache DB and initialize schema."""
        if self._conn is not None:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute(SCHEMA_SQL)
        # Migrate existing DBs: add bitrate column if missing
        try:
            conn.execute(
                "ALTER TABLE tag_cache ADD COLUMN bitrate INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.commit()
        self._conn = conn

    def close(self) -> None:
        """Close the active DB connection."""
        if self._conn is None:
            return
        self._conn.close()
        self._conn = None

    def get(self, path: str | Path, mtime_ns: int, size: int) -> TagData | None:
        """Return cached tags when path and fingerprint match."""
        row = self._conn_or_raise().execute(
            """
            SELECT
                title, artist, album, albumartist,
                track, disc, year, genre, composer,
                duration, bitrate, artwork_data, artwork_mime
            FROM tag_cache
            WHERE path = ? AND mtime_ns = ? AND size = ?
            """,
            (self._normalize_path(path), int(mtime_ns), int(size)),
        ).fetchone()
        if row is None:
            return None
        artwork = row[11]
        return TagData(
            title=str(row[0] or ""),
            artist=str(row[1] or ""),
            album=str(row[2] or ""),
            albumartist=str(row[3] or ""),
            track=int(row[4] or 0),
            disc=int(row[5] or 0),
            year=int(row[6] or 0),
            genre=str(row[7] or ""),
            composer=str(row[8] or ""),
            duration=float(row[9] or 0.0),
            bitrate=int(row[10] or 0),
            artwork_data=bytes(artwork) if artwork is not None else None,
            artwork_mime=str(row[12] or ""),
        )

    def put(self, path: str | Path, mtime_ns: int, size: int, tags: TagData) -> None:
        """Upsert one cache record."""
        self.put_many([(path, mtime_ns, size, tags)])

    def put_many(
        self,
        entries: Iterable[tuple[str | Path, int, int, TagData]],
    ) -> None:
        """Batch upsert cache records."""
        rows = [
            (
                self._normalize_path(path),
                int(mtime_ns),
                int(size),
                tags.title,
                tags.artist,
                tags.album,
                tags.albumartist,
                int(tags.track),
                int(tags.disc),
                int(tags.year),
                tags.genre,
                tags.composer,
                float(tags.duration),
                int(tags.bitrate),
                tags.artwork_data,
                tags.artwork_mime,
            )
            for path, mtime_ns, size, tags in entries
        ]
        if not rows:
            return
        conn = self._conn_or_raise()
        conn.executemany(
            """
            INSERT INTO tag_cache (
                path, mtime_ns, size,
                title, artist, album, albumartist,
                track, disc, year, genre, composer,
                duration, bitrate, artwork_data, artwork_mime
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                mtime_ns = excluded.mtime_ns,
                size = excluded.size,
                title = excluded.title,
                artist = excluded.artist,
                album = excluded.album,
                albumartist = excluded.albumartist,
                track = excluded.track,
                disc = excluded.disc,
                year = excluded.year,
                genre = excluded.genre,
                composer = excluded.composer,
                duration = excluded.duration,
                bitrate = excluded.bitrate,
                artwork_data = excluded.artwork_data,
                artwork_mime = excluded.artwork_mime
            """,
            rows,
        )
        conn.commit()

    def invalidate(self, path: str | Path) -> None:
        """Remove one path from cache."""
        self.invalidate_many([path])

    def invalidate_many(self, paths: Iterable[str | Path]) -> None:
        """Remove multiple paths from cache."""
        rows = [(self._normalize_path(path),) for path in paths]
        if not rows:
            return
        conn = self._conn_or_raise()
        conn.executemany("DELETE FROM tag_cache WHERE path = ?", rows)
        conn.commit()

    def clear(self) -> None:
        """Delete all cache entries."""
        conn = self._conn_or_raise()
        conn.execute("DELETE FROM tag_cache")
        conn.commit()

    def _conn_or_raise(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("TagCache is not open")
        return self._conn

    @staticmethod
    def _normalize_path(path: str | Path) -> str:
        try:
            return str(Path(path).resolve())
        except Exception:
            return str(Path(path))
