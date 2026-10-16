# MusicOrg — Project Context

## Project Overview

**MusicOrg** is a PySide6 desktop application for music library management. It provides a Qt-based GUI for scanning, tagging, organizing, and syncing audio files.

### Core Capabilities
- **Scanning**: Recursive directory scanning for audio files (`.mp3`, `.flac`, `.m4a`, `.ogg`, `.opus`, `.wav`, `.aiff`, `.wv`)
- **Tag Editing**: View/edit metadata tags and embedded artwork (single-file and bulk operations)
- **Auto-Tagging**: Metadata lookup from MusicBrainz and Discogs
- **Library Browser**: Explore by artist/album with album cards and artwork backdrop
- **Duplicate Finder**: Identify and manage duplicate tracks
- **Sync Planner**: Non-destructive sync operations with tag-based destination paths
- **Theme System**: Plugin-based theme framework with runtime loading

### Tech Stack
- **Language**: Python 3.10+
- **UI Framework**: PySide6 (Qt 6.6+)
- **Audio Tagging**: `music-tag`, `mutagen`
- **Metadata APIs**: `musicbrainzngs`, `python3-discogs-client`
- **Testing**: pytest, pytest-qt

---

## Project Structure

```
musicorg/
├── musicorg/                 # Main package
│   ├── __main__.py           # Entry point (python -m musicorg)
│   ├── app.py                # QApplication bootstrap
│   ├── runtime_paths.py      # Path resolution (source/frozen modes)
│   ├── config/
│   │   └── settings.py       # QSettings wrapper for app config
│   ├── core/                 # Business logic
│   │   ├── scanner.py        # File system audio file scanner
│   │   ├── tagger.py         # Tag read/write operations
│   │   ├── autotagger.py     # MusicBrainz/Discogs lookup
│   │   ├── syncer.py         # Sync planning/execution
│   │   ├── duplicate_finder.py
│   │   └── tag_cache.py      # SQLite cache for faster scans
│   ├── ui/                   # User interface
│   │   ├── main_window.py    # Main window with sidebar navigation
│   │   ├── source_panel.py   # Source browser panel
│   │   ├── tag_editor_panel.py
│   │   ├── autotag_panel.py
│   │   ├── sync_panel.py
│   │   ├── duplicates_panel.py
│   │   ├── artwork_downloader_panel.py
│   │   ├── settings_dialog.py
│   │   ├── shortcuts_dialog.py
│   │   ├── theme_dialog.py
│   │   ├── keybindings.py    # Keyboard shortcut registry
│   │   ├── models/           # Qt models (file_table_model.py, match_model.py)
│   │   ├── widgets/          # Reusable widgets (album_browser, file_table, etc.)
│   │   ├── themes/           # Theme framework (registry, loader, service)
│   │   └── assets/           # Icons, images
│   ├── workers/              # Threaded background workers
│   │   ├── base_worker.py    # Base class with Qt signals
│   │   ├── scan_worker.py
│   │   ├── tag_read_worker.py
│   │   ├── tag_write_worker.py
│   │   ├── autotag_worker.py
│   │   ├── sync_worker.py
│   │   ├── duplicate_worker.py
│   │   └── artwork_worker.py
│   └── plugins/              # Plugin runtime directory (git-ignored)
│       └── builtin/          # Built-in theme plugins
├── tests/                    # Unit tests (pytest)
├── docs/                     # Documentation
│   └── themes/               # Theme author documentation
├── scripts/                  # Build/deployment scripts
│   ├── build-windows.ps1     # PyInstaller build script
│   └── smoke-test-exe.ps1    # Post-build smoke test
├── packaging/                # PyInstaller specs (if present)
├── pyproject.toml            # Project metadata & build config
├── requirements.txt          # Runtime dependencies
└── README.md                 # User-facing documentation
```

---

## Building and Running

### Development Setup
```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Unix

# Install dependencies
pip install -r requirements.txt

# Optional: install dev dependencies
pip install -e ".[dev]"
```

### Run Application
```bash
# From source
python -m musicorg

# If installed as package
musicorg
```

### Testing
```bash
# Run all tests
python -m pytest -q

# Verbose
python -m pytest -v
```

### Building Executable (Windows)
```bash
# Requires .venv-build environment
powershell -ExecutionPolicy Bypass -File scripts/build-windows.ps1
```

---

## Development Conventions

### Code Style
- Type hints throughout (see `from __future__ import annotations`)
- Dataclasses for simple data containers (`AudioFile`, etc.)
- Qt signal/slot pattern for worker threads
- `QSettings` for persistent configuration

### Architecture Patterns
- **Worker Pattern**: Long-running operations use `BaseWorker` + `QThread`
- **Panel-based UI**: Main window uses stacked panels with sidebar navigation
- **Service Layer**: Theme management via `ThemeService` + `ThemeRegistry`
- **Runtime Path Abstraction**: `runtime_paths.py` handles source vs. frozen (PyInstaller) layouts

### Testing Practices
- pytest fixtures for temp directories and test data
- Unit tests for core modules (`scanner`, `tagger`, `syncer`, etc.)
- Test files prefixed with `test_*.py` in `tests/`

### Key Configuration
- App settings: `QSettings("MusicOrg", "MusicOrg")`
- Tag cache: SQLite DB under user app data directory
- Themes: Builtin + user theme directories with plugin loading

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `musicorg/__main__.py` | Entry point for `python -m musicorg` |
| `musicorg/app.py` | QApplication initialization, theme service setup |
| `musicorg/ui/main_window.py` | Main window, sidebar nav, panel stack |
| `musicorg/core/scanner.py` | Audio file discovery |
| `musicorg/core/tag_cache.py` | SQLite cache for scan performance |
| `musicorg/workers/base_worker.py` | Thread worker base with Qt signals |
| `musicorg/config/settings.py` | QSettings wrapper |
| `scripts/build-windows.ps1` | PyInstaller build automation |

---

## Notes
- **Supported formats**: `.mp3`, `.flac`, `.m4a`, `.ogg`, `.opus`, `.wav`, `.aiff`, `.wv`
- **Sync is non-destructive**: Source files are not moved/deleted
- **Theme plugins**: Stored in `musicorg/plugins/` (git-ignored, runtime-only)
- **Windows-focused**: Build scripts and path handling optimized for Windows
