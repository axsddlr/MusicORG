<p align="center">
  <img src="musicorg/ui/assets/musicorg.png" alt="MusicOrg logo" width="96" />
</p>

<h1 align="center">MusicOrg</h1>

<p align="center">
  PySide6 desktop app for music library management.
</p>

## Overview
MusicOrg is a desktop workflow for:
- Scanning source folders for audio files and building a persistent library database
- Viewing and editing tags (including embedded artwork)
- Auto-tagging from MusicBrainz and Discogs
- Exploring library content by artist, album, genre, year, and format
- Planning and running non-destructive sync operations with 4-tier matching
- Finding and reviewing duplicate tracks with side-by-side tag comparison
- Batch metadata operations (find/replace, regex, case transform)
- Playlist management with on-demand album browser loading
- Custom user-defined tags per track

## Current Features

### Library Management
- **Persistent LibraryDatabase** — normalized SQLite schema with artists, albums, tracks, and deduplicated artwork. Replaces transient in-memory indexes and tag caches.
- **Instant search** — type-ahead search across artist, album, and track fields with 300ms debounce.
- **Column browser** — browse by Genre, Year, or Format via clickable filter chips with count badges.
- **Auto-sweep folder monitoring** — scanned directories are watched via `QFileSystemWatcher`; new/changed/removed files are detected within 2 seconds without manual re-scan.
- **Playlist management** — create, delete, and load playlists from the left sidebar. Click any playlist to show its tracks in the album browser.
- **Custom tags** — user-defined key-value fields per track via JSON blob column. Add/edit/remove in the Tag Editor.

### Tag Editor
- Single-file and bulk changed-field writes
- Artwork preview showing current embedded cover or newly selected replacement
- Custom tags section with dynamic add/remove key-value rows
- Fast tag reads via LibraryDatabase — no `music_tag.load_file()` on every navigation

### Auto-Tag & Artwork
- **MusicBrainz** and **Discogs** metadata lookup for albums and single tracks
- Provider diagnostics with per-source error reporting
- Artwork search, preview, and apply to selected files

### Duplicate Finder
- Union-Find based grouping with priority-aware keep selection (FLAC > MP3, by bitrate, by size)
- Three-tier confidence system: exact hash (1.0) > tag identity (0.9) > filename/path (0.6)
- **Side-by-side tag comparison** — select any duplicate pair to see all tag fields compared with color-coded differences

### Sync
- Four-tier matching: path → track UID → identity key → exact SHA1 hash
- Reverse sync support (dest → source by track identity)
- Batch processing in 1000-file chunks to bound memory usage
- Bounded hash caches (4096 entries) with oldest-entry eviction
- Cancellation check during file hashing — large files don't block the UI

### General
- **Batch Tag Operations** — find-and-replace, regex replace, uppercase, lowercase, title case, trim, and clear across selected files. Preview before applying.
- **Library Tools** — statistics dashboard (tracks/albums/artists, duration, size, top genres, format/year distribution), health scan (missing titles, mixed artists, low bitrate, missing artwork), CSV export of all tracks.
- **Keyboard Shortcut Editor** — click any shortcut to record a new key combination. Reset all to defaults. Conflicts are validated on save.
- **Theme framework** — plugin-based with runtime loading and validation. Six built-in themes including Spotify Dark, Nord Fjord, Synthwave Dusk, Solar Flare, Emerald Forest, and Arctic Light.
- Background workers for scan/read/write/search/sync tasks
- Windows-style selection behavior (Ctrl toggle, Shift range, Ctrl+Shift additive range)
- Configurable album artwork click behavior (single click, double click, or off)

## Requirements
- Python `3.10+`
- OS with Qt/PySide6 support (Windows recommended from current implementation)

## Installation
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Optional dev dependencies:
```bash
pip install -e ".[dev]"
```

## Run
```bash
python -m musicorg
```

## Quick Workflow
1. Open **Source**, select your library directory, and click **Scan**.
2. Browse by Artist (left sidebar) or use **Genre / Year / Format** filter chips.
3. Type in the **search bar** to instantly filter across artist/album/track.
4. Build your selection:
   - `Ctrl + Left Click` toggles tracks
   - `Shift + Left Click` selects ranges
   - Album artwork click behavior follows **Settings > Preferences**
5. Right-click tracks/albums to open:
   - `Tag Editor`
   - `Auto-Tag`
   - `Artwork Downloader`
6. Use **Tools** menu for:
   - **Batch Tag Operations** — mass metadata transforms
   - **Library Tools** — stats, health scan, CSV export
   - **Customize Shortcuts** — rebind any key
   - **Rename Files to Match Tags** — rename files from their tag values
7. Use **Sync** to plan and copy files to a destination structure.
8. Use **Duplicates** to review groups and compare tags side-by-side.
9. Create **Playlists** from the left sidebar to organize tracks.

## Configuration
- App settings are stored via `QSettings`.
- Discogs token can be configured in **Settings > Preferences**.
- Artwork click selection behavior can be configured in **Settings > Preferences**.
- View keyboard shortcuts in **Help > Keyboard Shortcuts**.
- Customize keyboard shortcuts in **Tools > Customize Shortcuts**.
- Library database, tag cache, and track identity DB are managed under user app data.

## Testing
```bash
python -m pytest -q
```

## Project Layout
```text
musicorg/
|-- musicorg/
|   |-- core/         # scanner, tagger, autotagger, sync, duplicate, library_db
|   |-- ui/           # panels, dialogs, widgets, models, themes
|   |-- workers/      # threaded workers for background operations
|   `-- config/       # application settings (QSettings wrapper)
`-- tests/            # 249+ unit tests
```

## Libraries

| Library | Version | Purpose |
|---|---|---|
| [PySide6](https://doc.qt.io/qtforpython/) | `>=6.6.0` | Qt-based UI framework |
| [music-tag](https://github.com/KristoforMaynard/music-tag) | `>=0.4.3` | Unified audio tag read/write (MP3, FLAC, M4A, OGG, OPUS, WAV, AIFF, WV) |
| [mutagen](https://mutagen.readthedocs.io/) | `>=1.47.0` | Low-level audio metadata (used internally by music-tag) |
| [musicbrainzngs](https://python-musicbrainzngs.readthedocs.io/) | `>=0.7.1` | MusicBrainz metadata lookup for auto-tagging |
| [python3-discogs-client](https://github.com/discogs/discogs_client) | `>=2.3.15` | Discogs metadata lookup for auto-tagging |
| [send2trash](https://github.com/arsenetar/send2trash) | `>=1.8.0` | Safe file deletion to system trash *(optional)* |

**Dev dependencies:** `pytest>=8.0`, `pytest-qt>=4.4`

## Notes
- Supported audio formats: `.mp3`, `.flac`, `.m4a`, `.ogg`, `.opus`, `.wav`, `.aiff`, `.wv`, `.ape`, `.tak`
- Sync is non-destructive copy (source files are not moved/deleted)
- Tools menu actions are enabled only when at least one file is selected
- Library database (`library.db`) is created automatically after the first scan — replaces the older `tag_cache.db` and `track_identity.db` structures
- Artwork is deduplicated by SHA256 hash across the entire library
