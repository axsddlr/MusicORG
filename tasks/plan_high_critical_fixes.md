# Plan: Fix C2 + H2 + H3 + H4 + H5 + H6

**Created:** 2026-03-14
**Issues:** C2 (connection leak), H2 (unbounded cache), H3 (refactor plan_sync), H4 (cancellation), H5 (MusicOrgError), H6 (scanner OSError logging)

---

## Execution Order

Ordered from safest/smallest to riskiest/largest to keep diffs reviewable:

1. **H6** — Scanner logging (5 min, 1 file, 2 lines changed)
2. **C2** — Connection leak fix (10 min, 1 file, ~6 lines changed)
3. **H4** — Cancellation in `_file_sha1()` (30 min, 1 file)
4. **H2** — Bounded hash caches (20 min, 1 file)
5. **H5** — `MusicOrgError` in autotagger (45 min, 2 files)
6. **H3** — Refactor `plan_sync()` (60 min, 1 file, behavioral no-op)

Steps 1–4 are independent and can each be verified individually. Steps 5–6 follow after tests confirm 1–4 pass.

---

## Step 1 — H6: Log skipped files in scanner

**File:** `musicorg/core/scanner.py`

Add `import logging` and `_logger = logging.getLogger(__name__)`. Replace both silent `except OSError: continue` with logged version.

```python
# scan()
try:
    results.append(AudioFile(path=p))
except OSError as e:
    _logger.debug("Skipping %s: %s", p, e)
    continue

# scan_iter()
try:
    yield AudioFile(path=p)
except OSError as e:
    _logger.debug("Skipping %s: %s", p, e)
    continue
```

**Test:** Add `test_scanner_skips_inaccessible_file` in `tests/test_scanner.py` — create a real file, remove read permissions (skip on Windows CI), verify `scan()` returns empty list without raising.

---

## Step 2 — C2: Fix SQLite connection leak in TrackIdentityIndex.open()

**File:** `musicorg/core/track_identity_index.py`

Wrap post-connect initialization in try/except. Close `conn` on any failure before re-raising so the file descriptor is not leaked.

```python
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
```

**Test:** Add `test_track_identity_index_open_cleans_up_on_schema_failure` in `tests/test_track_identity_index.py` — patch `sqlite3.Connection.executescript` to raise, call `open()`, assert it raises and that a subsequent `open()` call succeeds (proves the leaked conn didn't corrupt state).

---

## Step 3 — H4: Cancellation check in `_file_sha1()`

**File:** `musicorg/core/syncer.py`

Add `cancel_check: Callable[[], bool] | None = None` to `_file_sha1()`. After each chunk, if `cancel_check()` returns True, return `None` (incomplete — do **not** cache a partial result).

```python
def _file_sha1(
    path: Path,
    cache: dict[Path, str],
    cancel_check: Callable[[], bool] | None = None,
) -> str | None:
    cached = cache.get(path)
    if cached is not None:
        return cached
    try:
        digest = hashlib.sha1(usedforsecurity=False)
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                if cancel_check and cancel_check():
                    return None
    except OSError:
        return None
    value = digest.hexdigest()
    cache[path] = value
    return value
```

Propagate `cancel_check` through the call chain:

```python
def _get_or_compute_sha1(
    path, *, af, tags, hash_cache, identity_index,
    cancel_check: Callable[[], bool] | None = None,
) -> str | None:
    ...
    digest = _file_sha1(path, hash_cache, cancel_check=cancel_check)
    ...

def _ensure_hash_bucket(
    bucket, files_by_size_ext, audio_by_path, tags_by_path,
    hash_cache, hashes_by_size_ext, loaded_buckets, identity_index,
    cancel_check: Callable[[], bool] | None = None,
) -> set[str]:
    ...
    digest = _get_or_compute_sha1(
        path, af=af, tags=..., hash_cache=hash_cache,
        identity_index=identity_index, cancel_check=cancel_check,
    )
    ...
```

In `plan_sync()`, pass `cancel_check=lambda: self._cancelled` everywhere `_get_or_compute_sha1` and `_ensure_hash_bucket` are called (4 call sites).

**Note:** `execute_sync()` also calls `_file_sha1()` indirectly via `_file_sha1(item.source, source_hash_cache)`. Update that call site too.

**Test:** Add `test_file_sha1_returns_none_when_cancelled` — write a multi-MB file, set cancel immediately, verify result is `None` and cache is empty.

---

## Step 4 — H2: Bounded hash caches

**File:** `musicorg/core/syncer.py`

Add constant and helper after `_file_sha1`:

```python
_HASH_CACHE_MAX = 4096

def _bounded_cache_set(cache: dict[Path, str], key: Path, value: str) -> None:
    """Insert into cache, evicting the oldest entry if at capacity."""
    if len(cache) >= _HASH_CACHE_MAX:
        cache.pop(next(iter(cache)))  # dict preserves insertion order (Python 3.7+)
    cache[key] = value
```

Replace all `cache[path] = value` / `hash_cache[path] = existing` assignments in:
- `_file_sha1()` line `cache[path] = value` → `_bounded_cache_set(cache, path, value)`
- `_get_or_compute_sha1()` line `hash_cache[path] = existing` → `_bounded_cache_set(hash_cache, path, existing)`

No other cache types need bounding (identity candidates and tag caches are bounded by file count, which is expected to be reasonable).

**Test:** Add `test_hash_cache_bounded_at_max_size` — call `_bounded_cache_set` 5000 times, assert `len(cache) <= _HASH_CACHE_MAX`.

---

## Step 5 — H5: Replace RuntimeError with MusicOrgError in autotagger

**Files:** `musicorg/core/autotagger.py`, `musicorg/errors.py`

### 5a. Add import to autotagger.py

```python
from musicorg.errors import ErrorCode, MusicOrgError
```

### 5b. Replace 4 RuntimeError sites

| Line | Current | Replacement |
|------|---------|-------------|
| 146 | `raise RuntimeError(detail)` | `raise MusicOrgError(ErrorCode.OPERATION_FAILED, message=detail, details={"sources": list(source_errors.keys())})` |
| 213 | `raise RuntimeError(detail)` | `raise MusicOrgError(ErrorCode.OPERATION_FAILED, message=detail, details={"sources": list(source_errors.keys())})` |
| 246 | `raise RuntimeError(f"Apply match failed: {exc}") from exc` | `raise MusicOrgError(ErrorCode.OPERATION_FAILED, message=f"Apply match failed: {exc}", details={"cause": str(exc)}) from exc` |
| 884 | `raise RuntimeError("retry wrapper reached an unexpected state")` | `raise MusicOrgError(ErrorCode.OPERATION_FAILED, message="retry wrapper reached an unexpected state")` |

**Gotcha:** Any existing tests that do `pytest.raises(RuntimeError)` for these paths need to be updated to `pytest.raises(MusicOrgError)`. Check `tests/test_autotagger.py` before implementing.

**Test:** Add `test_search_album_raises_music_org_error_when_all_sources_fail` and `test_search_item_raises_music_org_error_when_all_sources_fail` — mock both MB and Discogs to raise, assert `MusicOrgError` (not `RuntimeError`) is raised and `error.code == ErrorCode.OPERATION_FAILED`.

---

## Step 6 — H3: Refactor plan_sync() into sub-methods

**File:** `musicorg/core/syncer.py`

### 6a. Add `_PlanContext` dataclass (module-level, before `SyncManager`)

```python
@dataclass
class _PlanContext:
    """Shared mutable state threaded through plan_sync sub-phases."""
    source_track_keys: set = field(default_factory=set)
    source_track_uids: set = field(default_factory=set)
    dest_track_uids: set = field(default_factory=set)
    source_identity_set: set = field(default_factory=set)
    dest_identity_set: set = field(default_factory=set)
    source_track_uid_by_path: dict = field(default_factory=dict)
    dest_track_uid_by_path: dict = field(default_factory=dict)
    source_identity_candidates_by_path: dict = field(default_factory=dict)
    dest_identity_candidates_by_path: dict = field(default_factory=dict)
    source_dir_keys: dict = field(default_factory=dict)
    dest_dir_keys: dict = field(default_factory=dict)
    source_audio_by_path: dict = field(default_factory=dict)
    dest_audio_by_path: dict = field(default_factory=dict)
    source_tag_cache: dict = field(default_factory=dict)
    dest_tag_cache: dict = field(default_factory=dict)
    source_files_by_size_ext: dict = field(default_factory=dict)
    dest_files_by_size_ext: dict = field(default_factory=dict)
    source_hashes_by_size_ext: dict = field(default_factory=dict)
    dest_hashes_by_size_ext: dict = field(default_factory=dict)
    source_hash_buckets_loaded: set = field(default_factory=set)
    dest_hash_buckets_loaded: set = field(default_factory=set)
    source_hash_cache: dict = field(default_factory=dict)
    dest_hash_cache: dict = field(default_factory=dict)
```

### 6b. Extract three private SyncManager methods

**`_prescan_dest(ctx, dest_files, identity_index)`** — current lines 419–473 (dest pre-scan loop). No return value; mutates `ctx`.

**`_scan_sources(ctx, source_files, dest_dir, identity_index, plan, progress_cb, step, total_steps) -> int`** — current lines 475–559 (source scan loop). Returns final `step` count.

**`_scan_reverse(ctx, dest_files, source_dir, identity_index, plan, progress_cb, step, total_steps)`** — current lines 561–614 (reverse scan loop). No return needed.

### 6c. Rewrite plan_sync() as orchestration (~35 lines)

```python
def plan_sync(self, source_dir, dest_dir, progress_cb=None, include_reverse=False) -> SyncPlan:
    source_dir = Path(source_dir)
    dest_dir = Path(dest_dir)
    self._cancelled = False

    source_files = FileScanner(source_dir).scan()
    dest_files = FileScanner(dest_dir).scan()
    total_steps = len(source_files) + (len(dest_files) if include_reverse else 0)
    plan = SyncPlan()
    ctx = _PlanContext()

    identity_index: TrackIdentityIndex | None = None
    if self._identity_db_path:
        try:
            identity_index = TrackIdentityIndex(self._identity_db_path)
            identity_index.open()
        except Exception as e:
            _logger.warning("Failed to open identity index %s: %s — matching will be limited", self._identity_db_path, e)

    try:
        self._prescan_dest(ctx, dest_files, identity_index)
        step = self._scan_sources(ctx, source_files, dest_dir, identity_index, plan, progress_cb, 0, total_steps)
        if include_reverse and not self._cancelled:
            self._scan_reverse(ctx, dest_files, source_dir, identity_index, plan, progress_cb, step, total_steps)
        return plan
    finally:
        if identity_index is not None:
            try:
                identity_index.close()
            except Exception as e:
                _logger.debug("identity_index.close failed: %s", e)
```

**Gotcha — cancel_check propagation:** After H4, the sub-methods will need `cancel_check=lambda: self._cancelled` threaded through to `_ensure_hash_bucket` calls. Implement H4 before H3 to avoid doing the propagation twice.

**Test:** All 41 existing syncer tests pass — this is the primary verification. No new tests needed for the refactor itself.

---

## Verification

After all steps:

```bash
python -m pytest tests/ -x -q
```

All 184 tests must pass. Additionally verify imports manually:

```python
python -c "from musicorg.core.scanner import FileScanner; from musicorg.core.autotagger import AutoTagger; from musicorg.errors import MusicOrgError, ErrorCode; print('OK')"
```

---

## Files Modified

| File | Steps |
|------|-------|
| `musicorg/core/scanner.py` | H6 |
| `musicorg/core/track_identity_index.py` | C2 |
| `musicorg/core/syncer.py` | H4, H2, H3 |
| `musicorg/core/autotagger.py` | H5 |
| `musicorg/errors.py` | H5 (only if new ErrorCode needed — currently no) |
| `tests/test_scanner.py` | H6 |
| `tests/test_track_identity_index.py` | C2 |
| `tests/test_syncer.py` | H4, H2 |
| `tests/test_autotagger.py` | H5 |
