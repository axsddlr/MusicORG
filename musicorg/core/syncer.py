"""Non-destructive sync: copy files from source to destination using tag-based structure."""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from musicorg.core.scanner import AudioFile, FileScanner
from musicorg.core.tagger import TagManager
from musicorg.core.text_utils import (
    LEADING_TRACK_PREFIX_RE as _LEADING_TRACK_PREFIX_RE,
    normalize_loose as _normalize_identity_component,
    path_artist_album_hints as _path_artist_album_hints,
)
from musicorg.core.track_identity_index import TrackIdentityIndex

_logger = logging.getLogger(__name__)

SYNC_MATCH_PATH = "path"
SYNC_MATCH_TRACK_UID = "track_uid"
SYNC_MATCH_IDENTITY = "identity_key"
SYNC_MATCH_EXACT_HASH = "exact_hash"


@dataclass
class SyncItem:
    """A single file copy operation."""

    source: Path
    dest: Path
    status: str = "pending"  # pending, copied, exists, error
    error: str = ""
    match_reason: str = ""

@dataclass
class SyncPlan:
    """The full plan for a sync operation."""

    items: list[SyncItem] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def to_copy(self) -> int:
        return sum(1 for i in self.items if i.status == "pending")

    @property
    def already_exists(self) -> int:
        return sum(1 for i in self.items if i.status == "exists")

    @property
    def errors(self) -> int:
        return sum(1 for i in self.items if i.status == "error")


def _sanitize_filename(name: str) -> str:
    """Remove/replace characters illegal in Windows file names."""
    # Replace illegal chars with underscore
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    # Remove leading/trailing dots and spaces
    name = name.strip(". ")
    return name or "_"


def _sanitize_tag_value(value: str) -> str:
    """Replace path separator characters in a tag value so they are not treated as path components."""
    return value.replace("/", "_").replace("\\", "_")


def _build_dest_path(
    dest_root: Path,
    tags: dict,
    ext: str,
    path_format: str,
    source_path: Path | None = None,
) -> Path:
    """Build destination path from tags and format string.

    Validates that the resolved path stays within dest_root to prevent path traversal.
    """
    artist = _sanitize_tag_value(tags.get("albumartist") or tags.get("artist") or "Unknown Artist")
    album = _sanitize_tag_value(tags.get("album") or "Unknown Album")
    track = tags.get("track", 0)
    title = _sanitize_tag_value(
        tags.get("title") or (source_path.stem if source_path else None) or "Unknown Title"
    )
    year = tags.get("year", 0)

    # Build from format string by substituting variables
    path_str = path_format
    path_str = path_str.replace("$albumartist", artist)
    path_str = path_str.replace("$artist", artist)
    path_str = path_str.replace("$album", album)
    disc = tags.get("disc", 0)
    path_str = path_str.replace("$disc0", f"{disc:02d}" if disc else "01")
    path_str = path_str.replace("$disc-", f"{disc}-" if disc else "")
    path_str = path_str.replace("$disc", str(disc) if disc else "1")
    path_str = path_str.replace("$track", f"{track:02d}" if track else "00")
    path_str = path_str.replace("$title", title)
    path_str = path_str.replace("$year", str(year) if year else "0000")

    # Split into directory parts and filename, sanitize each
    parts = path_str.replace("\\", "/").split("/")
    sanitized = [_sanitize_filename(p) for p in parts]

    # Last part is filename, add extension
    sanitized[-1] = sanitized[-1] + ext

    result = dest_root.joinpath(*sanitized)

    # Validate result is under dest_root to prevent path traversal
    try:
        result.resolve().relative_to(dest_root.resolve())
    except ValueError:
        # Path resolves outside destination directory; fall back to safe default
        safe_filename = _sanitize_filename(source_path.stem if source_path else "unknown") + ext
        result = dest_root / safe_filename

    return result


def _normalize_track_value(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())



_HASH_CACHE_MAX = 4096
_SYNC_BATCH_SIZE = 1000


def _bounded_cache_set(cache: dict[Path, str], key: Path, value: str) -> None:
    """Insert into cache, evicting the oldest entry if at capacity."""
    if len(cache) >= _HASH_CACHE_MAX:
        cache.pop(next(iter(cache)))
    cache[key] = value


def _normalize_filename_for_match(path: Path) -> tuple[str, str]:
    """Normalize a filename for equivalence checks across prefix variants."""
    ext = path.suffix.lower()
    stem = path.stem
    without_prefix = _LEADING_TRACK_PREFIX_RE.sub("", stem, count=1)
    normalized = _normalize_track_value(_sanitize_filename(without_prefix))
    if normalized:
        return ext, normalized
    return ext, _normalize_track_value(_sanitize_filename(stem))


def _directory_file_keys(
    directory: Path,
    cache: dict[Path, set[tuple[str, str]]],
) -> set[tuple[str, str]]:
    cached = cache.get(directory)
    if cached is not None:
        return cached

    keys: set[tuple[str, str]] = set()
    if directory.is_dir():
        for child in directory.iterdir():
            if child.is_file():
                keys.add(_normalize_filename_for_match(child))
    cache[directory] = keys
    return keys


def _path_exists_or_equivalent(
    target_path: Path,
    directory_cache: dict[Path, set[tuple[str, str]]],
) -> bool:
    if target_path.exists():
        return True
    parent = target_path.parent
    if not parent.exists():
        return False
    key = _normalize_filename_for_match(target_path)
    return key in _directory_file_keys(parent, directory_cache)


def _track_identity(path: Path, tags: dict) -> tuple[str, str, str, int, int]:
    """Build a normalized identity key for matching tracks across trees."""
    artist = tags.get("albumartist") or tags.get("artist") or ""
    album = tags.get("album") or ""
    title = tags.get("title") or path.stem
    track = int(tags.get("track") or 0)
    disc = int(tags.get("disc") or 0)
    return (
        _normalize_track_value(str(artist)),
        _normalize_track_value(str(album)),
        _normalize_track_value(str(title)),
        track,
        disc,
    )


def _identity_tuple(path: Path, tags: dict) -> tuple[str, str, str]:
    """(norm_artist, norm_album, norm_title) for loose cross-directory matching."""
    artist = tags.get("albumartist") or tags.get("artist") or ""
    album = tags.get("album") or ""
    title = tags.get("title") or path.stem
    return (
        _normalize_identity_component(str(artist)),
        _normalize_identity_component(str(album)),
        _normalize_identity_component(str(title)),
    )



def _identity_candidates(path: Path, tags: dict) -> set[tuple[str, str, str]]:
    """Build multiple identity candidates from tags and path hints."""
    path_artist, path_album = _path_artist_album_hints(path)
    artist_values = {
        _normalize_identity_component(str(v))
        for v in (tags.get("albumartist"), tags.get("artist"), path_artist)
        if v
    }
    album_values = {
        _normalize_identity_component(str(v))
        for v in (tags.get("album"), path_album)
        if v
    }
    filename_title = _normalize_filename_for_match(path)[1]
    title_values = {
        _normalize_identity_component(str(v))
        for v in (tags.get("title"), filename_title)
        if v
    }
    title_values.discard("")
    if not title_values:
        return set()

    # Include partial identities to handle missing/dirty tags in destination trees.
    artist_options = tuple(artist_values) + ("",)
    album_options = tuple(album_values) + ("",)
    candidates: set[tuple[str, str, str]] = set()
    for title in title_values:
        for artist in artist_options:
            for album in album_options:
                if not (artist or album):
                    continue
                candidates.add((artist, album, title))
    return candidates


def _identity_candidates_from_loose_key(loose_key: str) -> set[tuple[str, str, str]]:
    """Expand a stored loose key into direct + partial match tuples."""
    parts = (loose_key or "").split("||")
    if len(parts) != 3:
        return set()
    artist, album, title = (part.strip() for part in parts)
    if not title:
        return set()

    candidates: set[tuple[str, str, str]] = {(artist, album, title)}
    if artist:
        candidates.add((artist, "", title))
    if album:
        candidates.add(("", album, title))
    return {item for item in candidates if item[0] or item[1]}


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
    _bounded_cache_set(cache, path, value)
    return value


def _get_or_compute_sha1(
    path: Path,
    *,
    af: AudioFile,
    tags: dict,
    hash_cache: dict[Path, str],
    identity_index: TrackIdentityIndex | None,
    cancel_check: Callable[[], bool] | None = None,
) -> str | None:
    """Reuse cached/indexed hash when possible, then persist computed hashes."""
    cached = hash_cache.get(path)
    if cached is not None:
        return cached

    if identity_index is not None:
        try:
            existing = identity_index.get_content_sha1(path, af.mtime_ns, af.size)
        except Exception as e:
            _logger.debug("identity_index lookup failed for %s: %s", path, e)
            existing = ""
        if existing:
            _bounded_cache_set(hash_cache, path, existing)
            return existing

    digest = _file_sha1(path, hash_cache, cancel_check=cancel_check)
    if digest and identity_index is not None:
        try:
            identity_index.upsert(
                path,
                af.mtime_ns,
                af.size,
                tags,
                content_sha1=digest,
                use_path_hints=True,
            )
        except Exception as e:
            _logger.debug("identity_index upsert failed for %s: %s", path, e)
    return digest


def _ensure_hash_bucket(
    bucket: tuple[int, str],
    files_by_size_ext: dict[tuple[int, str], list[Path]],
    audio_by_path: dict[Path, AudioFile],
    tags_by_path: dict[Path, dict],
    hash_cache: dict[Path, str],
    hashes_by_size_ext: dict[tuple[int, str], set[str]],
    loaded_buckets: set[tuple[int, str]],
    identity_index: TrackIdentityIndex | None,
    cancel_check: Callable[[], bool] | None = None,
) -> set[str]:
    hashes = hashes_by_size_ext.setdefault(bucket, set())
    if bucket in loaded_buckets:
        return hashes

    for path in files_by_size_ext.get(bucket, []):
        af = audio_by_path.get(path)
        if af is None:
            continue
        digest = _get_or_compute_sha1(
            path,
            af=af,
            tags=tags_by_path.get(path, {}),
            hash_cache=hash_cache,
            identity_index=identity_index,
            cancel_check=cancel_check,
        )
        if digest:
            hashes.add(digest)

    loaded_buckets.add(bucket)
    return hashes


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


class SyncManager:
    """Plans and executes non-destructive file copy operations."""

    def __init__(
        self,
        path_format: str = "$albumartist/$album/$track $title",
        identity_db_path: str | Path | None = None,
    ) -> None:
        self._path_format = path_format
        self._tag_manager = TagManager()
        self._identity_db_path = Path(identity_db_path) if identity_db_path else None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def plan_sync(
        self,
        source_dir: str | Path,
        dest_dir: str | Path,
        progress_cb: Callable[[int, int, str], None] | None = None,
        include_reverse: bool = False,
    ) -> SyncPlan:
        """Build sync plan, optionally including reverse (dest->source) by track identity."""
        source_dir = Path(source_dir)
        dest_dir = Path(dest_dir)

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
                _logger.warning(
                    "Failed to open identity index %s: %s — matching will be limited",
                    self._identity_db_path, e,
                )
                identity_index = None

        try:
            self._prescan_dest(ctx, dest_files, identity_index)
            step = self._scan_sources(
                ctx, source_files, dest_dir, identity_index, plan, progress_cb, 0, total_steps,
            )
            if include_reverse and not self._cancelled:
                self._scan_reverse(
                    ctx, source_dir, dest_dir, source_files, dest_files,
                    identity_index, plan, progress_cb, step, total_steps,
                )
            return plan
        finally:
            if identity_index is not None:
                try:
                    identity_index.close()
                except Exception as e:
                    _logger.debug("identity_index.close failed: %s", e)

    def _prescan_dest(
        self,
        ctx: _PlanContext,
        dest_files: list[AudioFile],
        identity_index: TrackIdentityIndex | None,
    ) -> None:
        """Pre-scan destination tree: collect identity/hash signals."""
        for af in dest_files:
            ctx.dest_audio_by_path[af.path] = af
            bucket = (af.size, af.extension)
            ctx.dest_files_by_size_ext.setdefault(bucket, []).append(af.path)

            candidates = _identity_candidates(af.path, {})
            dest_tags: dict = {}
            record = None

            if identity_index is not None:
                try:
                    record = identity_index.get(af.path, af.mtime_ns, af.size)
                except Exception as e:
                    _logger.debug("identity_index.get failed for %s: %s", af.path, e)
                    record = None

            if record is not None:
                if record.track_uid:
                    ctx.dest_track_uids.add(record.track_uid)
                    ctx.dest_track_uid_by_path[af.path] = record.track_uid
                if record.content_sha1:
                    ctx.dest_hashes_by_size_ext.setdefault(bucket, set()).add(record.content_sha1)
                candidates.update(_identity_candidates_from_loose_key(record.loose_identity_key))
            else:
                try:
                    dest_tags = self._tag_manager.read(af.path).as_dict()
                except Exception as e:
                    _logger.debug("Failed to read tags for %s: %s", af.path, e)
                    dest_tags = {}
                candidates.update(_identity_candidates(af.path, dest_tags))

                if identity_index is not None:
                    try:
                        record = identity_index.upsert(
                            af.path,
                            af.mtime_ns,
                            af.size,
                            dest_tags,
                            use_path_hints=True,
                        )
                    except Exception as e:
                        _logger.debug("identity_index.upsert failed for %s: %s", af.path, e)
                        record = None
                    if record is not None:
                        if record.track_uid:
                            ctx.dest_track_uids.add(record.track_uid)
                            ctx.dest_track_uid_by_path[af.path] = record.track_uid
                        if record.content_sha1:
                            ctx.dest_hashes_by_size_ext.setdefault(bucket, set()).add(record.content_sha1)
                        candidates.update(_identity_candidates_from_loose_key(record.loose_identity_key))

            ctx.dest_tag_cache[af.path] = dest_tags
            ctx.dest_identity_candidates_by_path[af.path] = candidates
            ctx.dest_identity_set.update(candidates)

    def _scan_sources(
        self,
        ctx: _PlanContext,
        source_files: list[AudioFile],
        dest_dir: Path,
        identity_index: TrackIdentityIndex | None,
        plan: SyncPlan,
        progress_cb: Callable[[int, int, str], None] | None,
        step: int,
        total_steps: int,
    ) -> int:
        """Source pass: decide whether each item is pending vs already exists.

        Processes files in batches of _SYNC_BATCH_SIZE to bound memory usage.
        Batch-local state is cleared after each batch; cross-batch state
        (identity sets, UIDs, track keys) persists in ctx.
        """
        total_source = len(source_files)
        batch_start = 0

        while batch_start < total_source:
            if self._cancelled:
                break

            batch_end = min(batch_start + _SYNC_BATCH_SIZE, total_source)
            batch = source_files[batch_start:batch_end]

            # Build batch-local indexes
            batch_audio: dict[Path, AudioFile] = {}
            batch_tags: dict[Path, dict] = {}
            batch_files_by_size_ext: dict[tuple[int, str], list[Path]] = {}
            batch_uid_by_path: dict[Path, str] = {}
            batch_candidates_by_path: dict[Path, set[tuple[str, str, str]]] = {}
            batch_hash_cache: dict[Path, str] = {}

            for af in batch:
                if self._cancelled:
                    break
                batch_audio[af.path] = af
                bucket = (af.size, af.extension)
                batch_files_by_size_ext.setdefault(bucket, []).append(af.path)

                step += 1
                if progress_cb:
                    progress_cb(step, total_steps or 1, af.path.name)

                try:
                    source_tags = self._tag_manager.read(af.path).as_dict()
                except Exception as e:
                    _logger.debug("Failed to read tags for %s: %s", af.path, e)
                    source_tags = {}
                batch_tags[af.path] = source_tags

                ctx.source_track_keys.add(_track_identity(af.path, source_tags))

                source_candidates = _identity_candidates(af.path, source_tags)
                source_uid = ""

                if identity_index is not None:
                    try:
                        record = identity_index.upsert(
                            af.path,
                            af.mtime_ns,
                            af.size,
                            source_tags,
                            use_path_hints=True,
                        )
                    except Exception as e:
                        _logger.debug("identity_index.upsert failed for %s: %s", af.path, e)
                        record = None
                    if record is not None:
                        source_uid = record.track_uid
                        if record.content_sha1:
                            ctx.source_hashes_by_size_ext.setdefault(bucket, set()).add(record.content_sha1)
                        source_candidates.update(_identity_candidates_from_loose_key(record.loose_identity_key))

                if source_uid:
                    ctx.source_track_uids.add(source_uid)
                    batch_uid_by_path[af.path] = source_uid

                batch_candidates_by_path[af.path] = source_candidates
                ctx.source_identity_set.update(source_candidates)

            # Match batch items against destination
            for af in batch:
                if self._cancelled:
                    break
                source_tags = batch_tags.get(af.path, {})
                source_candidates = batch_candidates_by_path.get(af.path, set())
                source_uid = batch_uid_by_path.get(af.path, "")

                dest_path = _build_dest_path(dest_dir, source_tags, af.extension, self._path_format, af.path)
                item = SyncItem(source=af.path, dest=dest_path)

                if _path_exists_or_equivalent(dest_path, ctx.dest_dir_keys):
                    item.status = "exists"
                    item.match_reason = SYNC_MATCH_PATH
                elif source_uid and source_uid in ctx.dest_track_uids:
                    item.status = "exists"
                    item.match_reason = SYNC_MATCH_TRACK_UID
                elif source_candidates & ctx.dest_identity_set:
                    item.status = "exists"
                    item.match_reason = SYNC_MATCH_IDENTITY
                else:
                    source_sha = _get_or_compute_sha1(
                        af.path,
                        af=af,
                        tags=source_tags,
                        hash_cache=batch_hash_cache,
                        identity_index=identity_index,
                        cancel_check=lambda: self._cancelled,
                    )
                    if source_sha:
                        dest_hashes = _ensure_hash_bucket(
                            (af.size, af.extension),
                            ctx.dest_files_by_size_ext,
                            ctx.dest_audio_by_path,
                            ctx.dest_tag_cache,
                            ctx.dest_hash_cache,
                            ctx.dest_hashes_by_size_ext,
                            ctx.dest_hash_buckets_loaded,
                            identity_index,
                            cancel_check=lambda: self._cancelled,
                        )
                        if source_sha in dest_hashes:
                            item.status = "exists"
                            item.match_reason = SYNC_MATCH_EXACT_HASH
                plan.items.append(item)

            # Free batch-local memory
            batch_start = batch_end

        return step

    def _scan_reverse(
        self,
        ctx: _PlanContext,
        source_dir: Path,
        dest_dir: Path,
        source_files: list[AudioFile],
        dest_files: list[AudioFile],
        identity_index: TrackIdentityIndex | None,
        plan: SyncPlan,
        progress_cb: Callable[[int, int, str], None] | None,
        step: int,
        total_steps: int,
    ) -> None:
        """Reverse scan: find dest files not matched in source pass."""
        for af in dest_files:
            if self._cancelled:
                break

            step += 1
            if progress_cb:
                progress_cb(step, total_steps or 1, f"reverse: {af.path.name}")

            dest_tags = ctx.dest_tag_cache.get(af.path, {})
            track_key = _track_identity(af.path, dest_tags)
            if track_key in ctx.source_track_keys:
                continue

            dest_uid = ctx.dest_track_uid_by_path.get(af.path, "")
            if dest_uid and dest_uid in ctx.source_track_uids:
                continue

            dest_candidates = ctx.dest_identity_candidates_by_path.get(
                af.path,
                _identity_candidates(af.path, dest_tags),
            )
            if dest_candidates & ctx.source_identity_set:
                continue

            bucket = (af.size, af.extension)
            dest_sha = _get_or_compute_sha1(
                af.path,
                af=af,
                tags=dest_tags,
                hash_cache=ctx.dest_hash_cache,
                identity_index=identity_index,
                cancel_check=lambda: self._cancelled,
            )
            if dest_sha:
                source_hashes = _ensure_hash_bucket(
                    bucket,
                    ctx.source_files_by_size_ext,
                    ctx.source_audio_by_path,
                    ctx.source_tag_cache,
                    ctx.source_hash_cache,
                    ctx.source_hashes_by_size_ext,
                    ctx.source_hash_buckets_loaded,
                    identity_index,
                    cancel_check=lambda: self._cancelled,
                )
                if dest_sha in source_hashes:
                    continue

            ctx.source_track_keys.add(track_key)
            source_path = _build_dest_path(source_dir, dest_tags, af.extension, self._path_format, af.path)
            item = SyncItem(source=af.path, dest=source_path)
            if _path_exists_or_equivalent(source_path, ctx.source_dir_keys):
                item.status = "exists"
                item.match_reason = SYNC_MATCH_PATH
            plan.items.append(item)

    def execute_sync(
        self,
        plan: SyncPlan,
        progress_cb: Callable[[int, int, str], None] | None = None,
        skip_existing: bool = True,
    ) -> SyncPlan:
        """Execute the copy operations in the plan.

        Args:
            plan: The sync plan to execute.
            progress_cb: Optional callback(current, total, message) for progress updates.
            skip_existing: If True, skip files that already exist at destination.
                If False, overwrite existing files.
        """
        self._cancelled = False
        pending = [item for item in plan.items if item.status == "pending"]

        identity_index: TrackIdentityIndex | None = None
        if self._identity_db_path:
            try:
                identity_index = TrackIdentityIndex(self._identity_db_path)
                identity_index.open()
            except Exception as e:
                _logger.warning(
                    "Failed to open identity index %s: %s — SHA1 matching disabled",
                    self._identity_db_path, e,
                )
                identity_index = None

        source_hash_cache: dict[Path, str] = {}

        try:
            for i, item in enumerate(pending):
                if self._cancelled:
                    break

                if progress_cb:
                    progress_cb(i + 1, len(pending), item.source.name)

                # Extra safety check: verify destination doesn't exist unless overwriting.
                if skip_existing and item.dest.exists():
                    item.status = "exists"
                    if not item.match_reason:
                        item.match_reason = SYNC_MATCH_PATH
                    continue

                try:
                    item.dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(item.source), str(item.dest))
                    item.status = "copied"

                    if identity_index is not None:
                        try:
                            stat = item.dest.stat()
                            try:
                                tags = self._tag_manager.read(item.dest).as_dict()
                            except Exception as e:
                                _logger.debug("Failed to read tags for %s: %s", item.dest, e)
                                tags = {}
                            sha1 = (
                                _file_sha1(item.source, source_hash_cache, cancel_check=lambda: self._cancelled)
                                or ""
                            )
                            identity_index.upsert(
                                item.dest,
                                stat.st_mtime_ns,
                                stat.st_size,
                                tags,
                                content_sha1=sha1,
                                use_path_hints=True,
                            )
                        except Exception as e:
                            _logger.debug("identity_index.upsert failed for %s: %s", item.dest, e)
                except Exception as e:
                    item.status = "error"
                    item.error = str(e)

            return plan
        finally:
            if identity_index is not None:
                try:
                    identity_index.close()
                except Exception as e:
                    _logger.debug("identity_index.close failed: %s", e)




