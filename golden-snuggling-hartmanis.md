# MusicOrg — PySide6 Desktop UI for Beets

## Context

The goal is to build a desktop application that wraps the [beets](https://github.com/beetbox/beets) music library manager, providing a GUI for:
- **ID3 tag reading/editing** for MP3 and FLAC files
- **Auto-tagging** via MusicBrainz + Discogs
- **Directory sync** — non-destructive copy from source to destination using `Artist/Album/Track` structure

The project is a fresh start (empty directory). Technology: **PySide6 (Qt6)** with direct Python integration to beets' library API.

---

## Project Structure

```
musicorg/
├── musicorg/
│   ├── __init__.py              # Version string
│   ├── __main__.py              # Entry point: python -m musicorg
│   ├── app.py                   # QApplication bootstrap, init beets config + library
│   │
│   ├── core/                    # Non-UI logic (beets integration)
│   │   ├── __init__.py
│   │   ├── beets_config.py      # Generate/manage beets config.yaml
│   │   ├── library.py           # Wrapper around beets.library.Library
│   │   ├── scanner.py           # Walk dirs, find .mp3/.flac files
│   │   ├── tagger.py            # Read/write tags via beets Item + mutagen
│   │   ├── autotagger.py        # MusicBrainz/Discogs lookup via beets autotag API
│   │   └── syncer.py            # Plan & execute non-destructive file copy
│   │
│   ├── ui/                      # PySide6 UI layer
│   │   ├── __init__.py
│   │   ├── main_window.py       # QMainWindow with QTabWidget
│   │   ├── source_panel.py      # Tab 1: browse source dir, scan files, show table
│   │   ├── tag_editor_panel.py  # Tab 2: view/edit ID3 tags per file
│   │   ├── autotag_panel.py     # Tab 3: search MusicBrainz/Discogs, pick match, apply
│   │   ├── sync_panel.py        # Tab 4: configure dirs, plan sync, execute copy
│   │   ├── settings_dialog.py   # Preferences dialog (dirs, Discogs token, path format)
│   │   ├── widgets/
│   │   │   ├── __init__.py
│   │   │   ├── file_table.py    # QTableView for audio file listings
│   │   │   ├── tag_form.py      # QFormLayout for tag field editing
│   │   │   ├── match_list.py    # Table for displaying match candidates
│   │   │   ├── progress_bar.py  # Progress indicator widget
│   │   │   └── dir_picker.py    # Directory picker (line edit + browse button)
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── file_table_model.py  # QAbstractTableModel for file list
│   │       └── match_model.py       # QAbstractTableModel for match candidates
│   │
│   ├── workers/                 # QThread workers for background ops
│   │   ├── __init__.py
│   │   ├── base_worker.py       # Base class with signals (progress, finished, error)
│   │   ├── scan_worker.py       # Scan directory for audio files
│   │   ├── tag_read_worker.py   # Read tags from files
│   │   ├── tag_write_worker.py  # Write tags to files
│   │   ├── autotag_worker.py    # Query MusicBrainz/Discogs
│   │   └── sync_worker.py       # Execute file copy operations
│   │
│   └── config/
│       ├── __init__.py
│       └── settings.py          # AppSettings via QSettings (source/dest dirs, tokens)
│
├── tests/
│   ├── __init__.py
│   ├── test_scanner.py
│   ├── test_tagger.py
│   ├── test_autotagger.py
│   ├── test_syncer.py
│   └── test_beets_config.py
│
├── requirements.txt
├── pyproject.toml
└── .gitignore
```

---

## Dependencies

```
PySide6>=6.6.0
beets>=2.0.0
python3-discogs-client>=2.3.15
mutagen>=1.47.0
PyYAML>=6.0
```

---

## Implementation Phases

### Phase 1: Foundation
1. **`pyproject.toml`**, **`requirements.txt`**, **`.gitignore`**
2. **`musicorg/__init__.py`** — version string
3. **`musicorg/__main__.py`** — `python -m musicorg` entry point
4. **`musicorg/config/settings.py`** — `AppSettings` class wrapping `QSettings` for source_dir, dest_dir, discogs_token, path_format, window_geometry
5. **`musicorg/core/beets_config.py`** — `BeetsConfigManager`: generates `%APPDATA%/musicorg/beets/config.yaml` from app settings, calls `beets.config.set_file()` to load it. Config enables Discogs plugin, sets path format `$albumartist/$album/$track $title`, sets `import.copy: true`

### Phase 2: Core Logic (no UI, testable independently)
6. **`musicorg/core/scanner.py`** — `FileScanner`: walks a directory, yields `AudioFile` dataclass (path, extension, size) for each `.mp3`/`.flac`
7. **`musicorg/core/tagger.py`** — `TagManager`: reads tags via `Item.from_path()` + `item.read()`, writes via `item.try_write()`. Uses `TagData` dataclass for clean data transfer
8. **`musicorg/core/autotagger.py`** — `AutoTagger`: calls `beets.autotag.match.tag_album()` for album matching and `tag_item()` for singles. Returns `MatchCandidate` dataclasses sorted by distance. Apply via `beets.autotag.apply_metadata()`
9. **`musicorg/core/syncer.py`** — `SyncManager`:
   - `plan_sync()`: scans source, reads tags, computes dest paths (`Artist/Album/01 Title.ext`), checks what exists → returns `SyncPlan`
   - `execute_sync()`: copies files via `shutil.copy2`, creates dirs, reports progress
   - Sanitizes filenames for Windows. Falls back to "Unknown Artist"/"Unknown Album" for missing tags
10. **`musicorg/core/library.py`** — `LibraryManager`: thin wrapper around `beets.library.Library`

### Phase 3: Threading Layer
11. **`musicorg/workers/base_worker.py`** — `BaseWorker(QObject)` with `WorkerSignals`: `started`, `progress(int,int,str)`, `finished(object)`, `error(str)`, `cancelled`. Pattern: `worker.moveToThread(thread)`, thread.started → worker.run
12. **Individual workers**: `ScanWorker`, `TagReadWorker`, `TagWriteWorker`, `AutoTagWorker`, `SyncWorker` — each wraps the corresponding core module method

### Phase 4: UI
13. **`musicorg/ui/models/`** — `FileTableModel` (columns: filename, artist, album, track#, format, size), `MatchModel` (columns: source, artist, album, year, match%)
14. **`musicorg/ui/widgets/`** — `DirPicker`, `FileTable`, `TagForm`, `MatchList`, `ProgressBar`
15. **`musicorg/ui/main_window.py`** — `QMainWindow` with `QTabWidget` (4 tabs), menu bar (File, Settings, Help), status bar with progress
16. **`musicorg/ui/source_panel.py`** — Dir picker + Scan button → table of discovered files with tags. Multi-select. Buttons to send selection to Tag Editor or Auto-Tag tabs
17. **`musicorg/ui/tag_editor_panel.py`** — Form with all tag fields (title, artist, album, albumartist, track, disc, year, genre, composer). Prev/Next navigation through selected files. Save/Revert buttons
18. **`musicorg/ui/autotag_panel.py`** — Search fields (artist, album) + Search button → match candidates table. Click candidate → track-level comparison table. "Apply Match" writes tags to files
19. **`musicorg/ui/sync_panel.py`** — Source/dest dir pickers + path format field. "Plan Sync" shows what will be copied/skipped/errored. "Start Sync" executes with progress bar. Cancel support
20. **`musicorg/ui/settings_dialog.py`** — Preferences: default dirs, Discogs token, path format template, beets DB location
21. **`musicorg/app.py`** — Creates `QApplication`, initializes `AppSettings` + `BeetsConfigManager` + `LibraryManager`, creates `MainWindow`, runs event loop

### Phase 5: Tests & Polish
22. Unit tests for core modules (scanner, tagger, syncer, beets_config)
23. Error handling refinement

---

## Key Design Decisions

**Beets integration approach**: Use beets' lower-level APIs (`tag_album`, `apply_metadata`, `Item.from_path`) instead of the `ImportSession` pipeline. The import pipeline is designed for terminal workflows with blocking prompts. The lower-level APIs let us separate "search" from "apply" for a GUI-friendly workflow.

**Sync is separate from auto-tag**: User workflow is browse → tag → sync. Tagging doesn't force a sync, and syncing uses whatever tags currently exist on files.

**Non-destructive sync**: Files are copied (not moved) from source to destination. Source directory is never modified. Destination uses `Artist/Album/Track` structure computed from tags.

**Threading**: QThread + moveToThread pattern. All beets operations (scan, tag read/write, MusicBrainz/Discogs lookup, file copy) run in background threads. Workers communicate via Qt signals only — no shared mutable state.

**Separate app config from beets config**: App settings in `QSettings` (fast, Qt-native). Beets config generated as YAML file (required by beets' plugin loading). Stored at `%APPDATA%/musicorg/beets/` to avoid conflicts with any system beets install.

---

## Verification Plan

1. **Install deps**: `pip install -r requirements.txt`
2. **Run the app**: `python -m musicorg`
3. **Test source scanning**: Point Source tab at a directory with MP3/FLAC files → verify table populates with filenames and existing tags
4. **Test tag editing**: Select a file → Tag Editor → modify a field → Save → re-read file in another tool (e.g., mp3tag) to confirm tags wrote correctly
5. **Test auto-tagging**: Select files from a known album → Auto-Tag → verify MusicBrainz candidates appear with correct match% → apply → verify tags updated
6. **Test Discogs**: Enter Discogs token in Settings → auto-tag → verify Discogs results appear alongside MusicBrainz
7. **Test sync**: Set source and dest dirs → Plan Sync → verify correct `Artist/Album/Track` paths shown → Start Sync → verify files copied to correct structure in dest dir
8. **Test idempotent sync**: Run sync again → verify already-synced files show as "Exists", no duplicate copies
9. **Run unit tests**: `python -m pytest tests/`
