# Changelog

All notable changes to this project are documented in this file.

## [0.7.2] - 2026-05-15

### Fixed
- SQLite connection leak in `TrackIdentityIndex.open()` — post-connect init failure no longer leaks file descriptors.
- Cancellation check added to `_file_sha1()` — large file hashing now supports early cancellation.
- Hash caches in `plan_sync()` bounded to 4096 entries — prevents OOM on large libraries.
- `RuntimeError` in autotagger replaced with `MusicOrgError(SEARCH_EXHAUSTED/PARSE_ERROR)` for typed error handling.
- Scanner OSError now logged at debug level instead of silently swallowed.
- `plan_sync()` refactored from 247-line monolith into `_prescan_dest()`, `_scan_sources()`, `_scan_reverse()` sub-methods.

### Added
- `ErrorCode.AUTOTAG_FAILED`, `ErrorCode.SEARCH_EXHAUSTED`, `ErrorCode.PARSE_ERROR` to error enum.
- `path_format` validation on setter — unknown variables raise `ValueError`.
- `conftest.py` with shared fixtures (`tmp_audio_file`, `tmp_library`) to reduce test boilerplate.
- Concurrent-access stress tests for `TagCache` and `TrackIdentityIndex`.
- Path deduplication in `TagReadWorker` — duplicate paths no longer cause redundant cache writes.
- Error code preserved through worker error signals (`[CODE] message` format).
- Return type hints added to UI model and panel methods.

### Changed
- Worker cleanup: `ThreadPoolExecutor.shutdown()` called immediately on cancellation to free memory.
- All lines exceeding 120 chars (PEP 8) wrapped across syncer, tagger, sync_panel, raw_files_panel, duplicate_worker.

## [0.7.1] - 2026-03-13

### Fixed
- Race condition in `TrackIdentityIndex` — `close()` could null `self._conn` between check and use.
- 20+ silent bare `except Exception: pass` blocks replaced with debug/warning logging.
- Consolidated duplicated text normalization and path-hint extraction into `text_utils.py`.

## [0.7.0] - 2026-03-06

### Added
- Persistent track identity index (`TrackIdentityIndex`) for cross-run matching.
- Identity-index matching pipeline in sync with match confidence tracking.
- Duplicate finder integration with identity index for improved detection.
- `safe_disconnect()` / `safe_disconnect_multiple()` helpers in `ui/utils.py`.

### Fixed
- Silent exception epidemic (~20 bare except blocks in syncer and duplicate_worker).
- Path traversal vulnerability in `_build_dest_path()` — resolved paths validated against dest_root.
- Race condition in identity index concurrent access.
- Fall back to filename stem when title tag absent.
- Sanitize path separators in tag values.

## [0.6.0] - 2026-02-15

### Added
- Plugin-based theme framework with runtime loading and apply support.
- Five additional built-in creative themes.
- Theme author documentation set (`docs/themes/*`) and framework planning docs.

### Changed
- Theme management moved under a dedicated Settings submenu in the UI.
- Theme loader hardening for safer custom theme-folder support.

### Documentation
- Refreshed README workflow references.
- Updated About dialog feature summary docs.

