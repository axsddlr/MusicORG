# Plan: Tier 0 — Persistent Library Database (A0.1)

**Objective:** Replace transient in-memory library representation (`_all_rows` / `_library_index` dicts) and two separate SQLite caches (`TagCache`, `TrackIdentityIndex`) with a single normalized `LibraryDatabase`.

---

## 1. Schema Design

One DB file at `{app_data_dir}/library.db` — replaces both `tag_cache.db` + `track_identity.db` + in-memory `_library_index`.

### artists
```sql
CREATE TABLE artists (
    artist_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    name_normalized TEXT NOT NULL,  -- for case-insensitive search/sort
    sort_name  TEXT NOT NULL DEFAULT '',
    thumbnail  BLOB,               -- first album artwork downsized
    UNIQUE(name)
);
```

### albums
```sql
CREATE TABLE albums (
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
```

### tracks
```sql
CREATE TABLE tracks (
    track_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id          INTEGER NOT NULL REFERENCES albums(album_id),
    path              TEXT NOT NULL UNIQUE,
    title             TEXT NOT NULL DEFAULT '',
    artist            TEXT NOT NULL DEFAULT '',
    track_number      INTEGER DEFAULT 0,
    disc_number       INTEGER DEFAULT 1,
    duration          REAL DEFAULT 0.0,
    bitrate           INTEGER DEFAULT 0,
    format            TEXT NOT NULL,  -- 'mp3', 'flac', etc.
    file_size         INTEGER NOT NULL DEFAULT 0,
    mtime_ns          INTEGER NOT NULL DEFAULT 0,
    content_sha1      TEXT NOT NULL DEFAULT '',
    rating            INTEGER DEFAULT 0,  -- 0-5
    play_count        INTEGER DEFAULT 0,
    skip_count        INTEGER DEFAULT 0,
    last_played       INTEGER DEFAULT 0,
    date_added        INTEGER NOT NULL DEFAULT (unixepoch()),
    date_modified     INTEGER NOT NULL DEFAULT (unixepoch()),
    artwork_id        INTEGER REFERENCES artwork(artwork_id)
);
CREATE INDEX idx_tracks_album_id ON tracks(album_id);
CREATE INDEX idx_tracks_path ON tracks(path);
CREATE INDEX idx_tracks_sha1 ON tracks(content_sha1);
```

### artwork (deduplicated blob store)
```sql
CREATE TABLE artwork (
    artwork_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256      TEXT NOT NULL UNIQUE,
    data        BLOB NOT NULL,
    mime        TEXT NOT NULL DEFAULT 'image/jpeg',
    width       INTEGER DEFAULT 0,
    height      INTEGER DEFAULT 0,
    refcount    INTEGER NOT NULL DEFAULT 1
);
```

### metadata (schema version + stats)
```sql
CREATE TABLE metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO metadata (key, value) VALUES ('schema_version', '1');
```

### Indexes
```sql
CREATE INDEX idx_tracks_album_id ON tracks(album_id);
CREATE INDEX idx_tracks_path ON tracks(path);
CREATE INDEX idx_tracks_sha1 ON tracks(content_sha1);
CREATE INDEX idx_albums_artist_id ON albums(artist_id);
CREATE INDEX idx_artwork_sha256 ON artwork(sha256);
```

---

## 2. Migration Strategy

### Phase 1 — Create library.db alongside existing caches
- New `LibraryDatabase` class in `core/library_db.py`
- On first scan, source creates library.db from tag reads (no migration from old caches)
- Old `tag_cache.db` + `track_identity.db` remain untouched during transition

### Phase 2 — Populate from old caches during migration window
- `LibraryDatabase` can optionally read from old `tag_cache` to pre-fill without re-reading tags
- Identity records (sha1, track_uid) migrate to `tracks.content_sha1`

### Phase 3 — Deprecate old caches (after 1+ release cycles)
- Stop opening `tag_cache.db` and `track_identity.db`
- Remove old classes

---

## 3. LibraryDatabase API

```python
class LibraryDatabase:
    def __init__(self, db_path: Path) -> None
    def open(self) -> None
    def close(self) -> None

    # -- Artist operations --
    def get_or_create_artist(self, name: str) -> int
    def get_artist(self, artist_id: int) -> ArtistRecord | None
    def search_artists(self, query: str) -> list[ArtistRecord]

    # -- Album operations --
    def get_or_create_album(self, artist_id: int, title: str, year: int = 0, genre: str = "") -> int
    def get_album(self, album_id: int) -> AlbumRecord | None
    def get_albums_by_artist(self, artist_id: int) -> list[AlbumRecord]
    def search_albums(self, query: str) -> list[AlbumRecord]

    # -- Track operations --
    def upsert_track(self, path: Path, tags: dict, hash_cache: dict | None = None) -> TrackRecord
    def get_track(self, path: Path) -> TrackRecord | None
    def get_tracks_by_album(self, album_id: int) -> list[TrackRecord]
    def search_tracks(self, query: str, filters: dict | None = None) -> list[TrackRecord]
    def remove_track(self, path: Path) -> None
    def remove_missing_tracks(self, known_paths: set[Path]) -> list[Path]

    # -- Artwork --
    def store_artwork(self, data: bytes, mime: str) -> int
    def get_artwork(self, artwork_id: int) -> bytes | None
    def link_artwork_to_track(self, track_id: int, artwork_id: int) -> None

    # -- Stats --
    def total_tracks(self) -> int
    def total_albums(self) -> int
    def total_artists(self) -> int
    def total_duration(self) -> float

    # -- Batch operations --
    def begin_batch(self) -> None   # explicit transaction
    def end_batch(self) -> None     # commit
```

Record types:
```python
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
```

---

## 4. Integration Points

### File Changes
| File | Change |
|------|--------|
| `core/library_db.py` | **NEW** — LibraryDatabase class + record types |
| `core/scanner.py` | Remove `FileScanner` — replace with `LibraryScanner` that writes to `LibraryDatabase` |
| `core/tag_cache.py` | No change (deprecated but kept for backward compat) |
| `core/track_identity_index.py` | No change (deprecated but kept for backward compat) |
| `ui/source_panel.py` | Replace `_all_rows` + `_library_index` with `LibraryDatabase.query(...)` |
| `ui/widgets/album_browser.py` | Accept `AlbumRecord` / `TrackRecord` lists instead of `FileTableRow` |
| `ui/widgets/album_card.py` | Same — adapt to new record types |
| `ui/tag_editor_panel.py` | Read/write through `LibraryDatabase`, fall back to file I/O |
| `workers/scan_worker.py` | Emit progress from library scan instead of tag-read pipeline |
| `workers/tag_read_worker.py` | Simplified — tag cache merge handled by library DB |
| `config/settings.py` | Add `library_db_path` property |

### Data Flow After A0.1
```
[File System]
     │
     ▼
LibraryScanner (replaces FileScanner)
  └── reads tags from file (or old tag_cache)
  └── upsert into LibraryDatabase
          │
          ▼
  LibraryDatabase ←──── SourcePanel (query-based, no _all_rows)
       │                      │
       │                      ├── AlbumBrowser (AlbumRecord → AlbumCard)
       │                      ├── TagEditorPanel (read/write via library)
       │                      └── Search/filter (SQL WHERE)
       │
       ├── SyncManager (reads library instead of rescanning)
       ├── DuplicateFinder (queries library for candidates)
       └── AutoTagger (reads tags from library, writes back)
```

---

## 5. Thread Safety

- `LibraryDatabase` uses `threading.RLock` (matching existing pattern)
- Read operations are not locked (SQLite WAL allows concurrent readers)
- Write operations acquire the lock (single writer at a time)
- Per-thread connections for concurrent reads (worker threads get their own read-only connections)

---

## 6. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| One DB or split? | **Single library.db** | Two caches were a historical accident; normalized schema handles all concerns |
| ORM or raw SQL? | **Raw SQL** | Avoids additional dependency; schema is simple enough |
| Artwork in DB or filesystem? | **DB (blob store)** | Deduplication via SHA256 works naturally; avoids stray file management |
| Normalize artist names? | **Stored normalized column** | Faster search than LOWER() on every query; built at insert time |
| Migration from old caches? | **Optional pre-fill** | New scans populate from scratch; user can run a "migrate" action to import old cache data |
| File changes or full record? | **File-level upsert** | Same as tag cache pattern: if mtime/size unchanged, skip re-read |
| Transaction strategy | **Explicit batch** | Scan uses begin_batch()/end_batch() for bulk inserts; single operations auto-commit |

---

## 7. Implementation Order

1. Create `core/library_db.py` with schema + record types + full API
2. Write tests for LibraryDatabase (CRUD, search, batch, thread safety)
3. Write `LibraryScanner` in `core/scanner.py` that populates library.db
4. Wire into source_panel — replace `_all_rows` with LibraryDatabase queries
5. Adapt album_browser/album_card to new record types
6. Wire into tag_editor_panel — read/write through library DB
7. Update scan_worker to use new scanner
8. Run full test suite, fix regressions
9. Benchmark: 1k, 10k, 100k tracks

**Estimated effort:** ~12-16 hours across all 9 steps.
