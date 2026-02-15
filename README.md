<p align="center">
  <img src="musicorg/ui/assets/musicorg.png" alt="MusicOrg logo" width="96" />
</p>

<h1 align="center">MusicOrg</h1>

<p align="center">
  PySide6 desktop app for music library management (MP3/FLAC).
</p>

## Overview
MusicOrg is a desktop workflow for:
- Scanning source folders for `.mp3` and `.flac` files
- Viewing and editing tags (including embedded artwork)
- Auto-tagging from MusicBrainz and Discogs
- Exploring library content by artist and album
- Planning and running non-destructive sync operations
- Finding duplicate tracks

## Current Features
- Source browser with artist filter, alphabet jump, album cards, and artwork backdrop
- Windows-style selection behavior (Ctrl toggle, Shift range, Ctrl+Shift additive range)
- Configurable album artwork click behavior (single click, double click, or off)
- Tag Editor dialog for single-file and bulk changed-field writes
- Tag Editor artwork preview showing current embedded cover or newly selected replacement
- Auto-Tag dialog with provider diagnostics and match application
- Artwork Downloader dialog with candidate search, preview, and apply to selected files
- Duplicate finder with keep/delete grouping logic
- Sync planner/executor with tag-based destination paths
- In-app Keyboard Shortcuts reference dialog (Help menu)
- Background workers for scan/read/write/search/sync tasks
- Tag cache for faster repeat scans

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

If installed as a package:
```bash
musicorg
```

## Quick Workflow
1. Open **Source** and select your library directory.
2. Click **Scan**.
3. Build your selection:
   - `Ctrl + Left Click` toggles tracks
   - `Shift + Left Click` selects ranges
   - Album artwork click behavior follows **Settings > Preferences**
4. Right-click tracks/albums to open:
   - `Tag Editor`
   - `Auto-Tag`
   - `Artwork Downloader`
5. In **Tag Editor**, use `Save` for one file or `Apply to Selected` for bulk edits.
6. Use **Sync** to plan and copy files to a destination structure.
7. Use **Duplicates** to review duplicate groups.

## Configuration
- App settings are stored via `QSettings`.
- Discogs token can be configured in **Settings > Preferences**.
- Artwork click selection behavior can be configured in **Settings > Preferences**.
- View keyboard behavior and app shortcuts in **Help > Keyboard Shortcuts**.
- Tag cache DB path is managed by the app under user app data.

## Testing
```bash
python -m pytest -q
```

## Project Layout
```text
musicorg/
|-- musicorg/
|   |-- core/        # scanner, tagger, autotagger, sync, duplicate logic
|   |-- ui/          # windows, dialogs, widgets, models, theme
|   |-- workers/     # threaded workers for long-running operations
|   `-- config/      # application settings
`-- tests/           # unit tests
```

## Notes
- Supported audio formats: `.mp3`, `.flac`
- Sync is non-destructive copy (source files are not moved/deleted)
- Tools menu actions are enabled only when at least one file is selected
