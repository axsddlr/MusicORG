"""Persistent track identity index for cross-run matching."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS track_identity (
    path                TEXT PRIMARY KEY,
    mtime_ns            INTEGER NOT NULL,
    size                INTEGER NOT NULL,
    track_uid           TEXT    NOT NULL,
    strict_identity_key TEXT    NOT NULL DEFAULT '',
    loose_identity_key  TEXT    NOT NULL DEFAULT '',
    title_key           TEXT    NOT NULL DEFAULT '',
    content_sha1        TEXT    NOT NULL DEFAULT '',
    duration            REAL    NOT NULL DEFAULT 0.0,
    updated_at          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_track_identity_uid ON track_identity(track_uid);
CREATE INDEX IF NOT EXISTS idx_track_identity_strict_key ON track_identity(strict_identity_key);
CREATE INDEX IF NOT EXISTS idx_track_identity_loose_key ON track_identity(loose_identity_key);
CREATE INDEX IF NOT EXISTS idx_track_identity_sha1 ON track_identity(content_sha1);
"""


@dataclass(slots=True)
class TrackIdentityRecord:
    path: Path
    mtime_ns: int
    size: int
    track_uid: str
    strict_identity_key: str
    loose_identity_key: str
    title_key: str
    content_sha1: str
    duration: float


def _get_value(tags: Any, key: str) -> Any:
    if isinstance(tags, Mapping):
        return tags.get(key)
    return getattr(tags, key, "")


from musicorg.core.text_utils import normalize_loose as _normalize_loose, path_artist_album_hints as _path_hints


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _coerce_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _identity_quality(strict_key: str, loose_key: str, title_key: str) -> int:
    """Score how informative an identity record is (higher is better)."""
    score = 0

    loose_parts = (loose_key or "").split("||")
    if len(loose_parts) == 3:
        if loose_parts[0]:
            score += 2
        if loose_parts[1]:
            score += 2
        if loose_parts[2]:
            score += 4
    elif title_key:
        score += 2

    strict_parts = (strict_key or "").split("||")
    if len(strict_parts) >= 6:
        if strict_parts[0]:
            score += 1
        if strict_parts[1]:
            score += 1
        if strict_parts[2]:
            score += 2
        if strict_parts[3] not in {"", "0"}:
            score += 1
        if strict_parts[4] not in {"", "0"}:
            score += 1
        if strict_parts[5] not in {"", "0"}:
            score += 1

    return score


def build_identity_fields(
    path: Path,
    tags: Any,
    *,
    content_sha1: str = "",
    use_path_hints: bool = True,
) -> tuple[str, str, str, str, float]:
    """Return (track_uid, strict_key, loose_key, title_key, duration)."""
    path_artist, path_album = _path_hints(path)

    artist_raw = _get_value(tags, "albumartist") or _get_value(tags, "artist") or ""
    album_raw = _get_value(tags, "album") or ""
    title_raw = _get_value(tags, "title") or path.stem

    if use_path_hints:
        artist_for_loose = artist_raw or path_artist
        album_for_loose = album_raw or path_album
    else:
        artist_for_loose = artist_raw
        album_for_loose = album_raw

    track = _coerce_int(_get_value(tags, "track"))
    disc = _coerce_int(_get_value(tags, "disc"))
    duration = _coerce_float(_get_value(tags, "duration"))
    duration_bucket = int(round(duration))

    strict_artist = _normalize_text(artist_raw)
    strict_album = _normalize_text(album_raw)
    strict_title = _normalize_text(title_raw)
    strict_key = "||".join(
        [
            strict_artist,
            strict_album,
            strict_title,
            str(track),
            str(disc),
            str(duration_bucket),
        ]
    )

    loose_artist = _normalize_loose(artist_for_loose)
    loose_album = _normalize_loose(album_for_loose)
    loose_title = _normalize_loose(title_raw)
    loose_key = "||".join([loose_artist, loose_album, loose_title])
    title_key = loose_title

    sha1 = (content_sha1 or "").strip().lower()
    if sha1:
        track_uid = f"sha1:{sha1}"
    elif strict_artist or strict_album or strict_title:
        track_uid = "meta:" + hashlib.sha1(strict_key.encode("utf-8"), usedforsecurity=False).hexdigest()
    else:
        resolved = str(path)
        track_uid = "path:" + hashlib.sha1(resolved.encode("utf-8"), usedforsecurity=False).hexdigest()

    return track_uid, strict_key, loose_key, title_key, duration


class TrackIdentityIndex:
    """SQLite-backed identity index keyed by file path + fingerprint."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    def open(self) -> None:
        with self._lock:
            if self._conn is not None:
                return
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.executescript(SCHEMA_SQL)
                conn.commit()
            except Exception:
                conn.close()
                raise
            self._conn = conn

    def close(self) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.close()
            self._conn = None

    def get(self, path: str | Path, mtime_ns: int, size: int) -> TrackIdentityRecord | None:
        with self._lock:
            row = self._conn_or_raise().execute(
                """
                SELECT
                    path, mtime_ns, size, track_uid,
                    strict_identity_key, loose_identity_key, title_key,
                    content_sha1, duration
                FROM track_identity
                WHERE path = ? AND mtime_ns = ? AND size = ?
                """,
                (self._normalize_path(path), int(mtime_ns), int(size)),
            ).fetchone()
            if row is None:
                return None
            return TrackIdentityRecord(
                path=Path(str(row[0])),
                mtime_ns=int(row[1]),
                size=int(row[2]),
                track_uid=str(row[3] or ""),
                strict_identity_key=str(row[4] or ""),
                loose_identity_key=str(row[5] or ""),
                title_key=str(row[6] or ""),
                content_sha1=str(row[7] or ""),
                duration=float(row[8] or 0.0),
            )

    def get_content_sha1(self, path: str | Path, mtime_ns: int, size: int) -> str:
        with self._lock:
            row = self._conn_or_raise().execute(
                """
                SELECT content_sha1
                FROM track_identity
                WHERE path = ? AND mtime_ns = ? AND size = ?
                """,
                (self._normalize_path(path), int(mtime_ns), int(size)),
            ).fetchone()
            if row is None:
                return ""
            return str(row[0] or "")

    def upsert(
        self,
        path: str | Path,
        mtime_ns: int,
        size: int,
        tags: Any,
        *,
        content_sha1: str = "",
        use_path_hints: bool = True,
    ) -> TrackIdentityRecord:
        normalized_path = self._normalize_path(path)
        with self._lock:
            conn = self._conn_or_raise()
            existing_row = conn.execute(
                """
                SELECT
                    mtime_ns, size, track_uid,
                    strict_identity_key, loose_identity_key, title_key,
                    content_sha1, duration
                FROM track_identity
                WHERE path = ?
                """,
                (normalized_path,),
            ).fetchone()
            same_fingerprint = bool(
                existing_row is not None
                and int(existing_row[0] or 0) == int(mtime_ns)
                and int(existing_row[1] or 0) == int(size)
            )
            existing_track_uid = str(existing_row[2] or "") if existing_row is not None else ""
            existing_strict_key = str(existing_row[3] or "") if existing_row is not None else ""
            existing_loose_key = str(existing_row[4] or "") if existing_row is not None else ""
            existing_title_key = str(existing_row[5] or "") if existing_row is not None else ""
            existing_sha1 = str(existing_row[6] or "") if existing_row is not None else ""
            existing_duration = float(existing_row[7] or 0.0) if existing_row is not None else 0.0

            sha1_value = content_sha1.strip().lower()
            if not sha1_value and same_fingerprint:
                sha1_value = existing_sha1.strip().lower()

            track_uid, strict_key, loose_key, title_key, duration = build_identity_fields(
                Path(normalized_path),
                tags,
                content_sha1=sha1_value,
                use_path_hints=use_path_hints,
            )

            incoming_quality = _identity_quality(strict_key, loose_key, title_key)
            existing_quality = _identity_quality(existing_strict_key, existing_loose_key, existing_title_key)
            if same_fingerprint and incoming_quality < existing_quality:
                strict_key = existing_strict_key
                loose_key = existing_loose_key
                title_key = existing_title_key
                duration = existing_duration
                if sha1_value:
                    track_uid = f"sha1:{sha1_value}"
                else:
                    track_uid = existing_track_uid

            conn.execute(
                """
                INSERT INTO track_identity (
                    path, mtime_ns, size,
                    track_uid, strict_identity_key, loose_identity_key,
                    title_key, content_sha1, duration, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    mtime_ns = excluded.mtime_ns,
                    size = excluded.size,
                    track_uid = excluded.track_uid,
                    strict_identity_key = excluded.strict_identity_key,
                    loose_identity_key = excluded.loose_identity_key,
                    title_key = excluded.title_key,
                    content_sha1 = excluded.content_sha1,
                    duration = excluded.duration,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_path,
                    int(mtime_ns),
                    int(size),
                    track_uid,
                    strict_key,
                    loose_key,
                    title_key,
                    sha1_value,
                    float(duration),
                    int(time.time()),
                ),
            )
            conn.commit()

        return TrackIdentityRecord(
            path=Path(normalized_path),
            mtime_ns=int(mtime_ns),
            size=int(size),
            track_uid=track_uid,
            strict_identity_key=strict_key,
            loose_identity_key=loose_key,
            title_key=title_key,
            content_sha1=sha1_value,
            duration=float(duration),
        )

    def _conn_or_raise(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("TrackIdentityIndex is not open")
        return self._conn

    @staticmethod
    def _normalize_path(path: str | Path) -> str:
        try:
            return str(Path(path).resolve())
        except Exception:
            return str(Path(path))
