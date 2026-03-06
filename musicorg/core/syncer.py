"""Non-destructive sync: copy files from source to destination using tag-based structure."""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from musicorg.core.scanner import AudioFile, FileScanner
from musicorg.core.tagger import TagManager
from musicorg.core.track_identity_index import TrackIdentityIndex


@dataclass
class SyncItem:
    """A single file copy operation."""

    source: Path
    dest: Path
    status: str = "pending"  # pending, copied, exists, error
    error: str = ""


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


def _normalize_identity_component(value: str) -> str:
    """Normalize text for identity matching across punctuation variants."""
    cleaned = re.sub(r"[^\w]+", " ", value.lower().replace("_", " "))
    return " ".join(cleaned.split())


_LEADING_TRACK_PREFIX_RE = re.compile(
    r"^\s*(?:(?:(?:#|\d{1,3})\s*(?:[-_.]|\u2013|\u2014)\s*)*(?:#|\d{1,3}))\s*(?:(?:[-_.]|\u2013|\u2014)\s*)?"
)


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


def _path_artist_album_hints(path: Path) -> tuple[str, str]:
    """Best-effort artist/album guesses from path segments."""
    album = ""
    artist = ""
    parent = path.parent
    if parent != path:
        album = parent.name
        grandparent = parent.parent
        if grandparent != parent:
            artist = grandparent.name
    return artist, album


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


def _file_sha1(path: Path, cache: dict[Path, str]) -> str | None:
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
    except OSError:
        return None
    value = digest.hexdigest()
    cache[path] = value
    return value


def _get_or_compute_sha1(
    path: Path,
    *,
    af: AudioFile,
    tags: dict,
    hash_cache: dict[Path, str],
    identity_index: TrackIdentityIndex | None,
) -> str | None:
    """Reuse cached/indexed hash when possible, then persist computed hashes."""
    cached = hash_cache.get(path)
    if cached is not None:
        return cached

    if identity_index is not None:
        try:
            existing = identity_index.get_content_sha1(path, af.mtime_ns, af.size)
        except Exception:
            existing = ""
        if existing:
            hash_cache[path] = existing
            return existing

    digest = _file_sha1(path, hash_cache)
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
        except Exception:
            pass
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
        )
        if digest:
            hashes.add(digest)

    loaded_buckets.add(bucket)
    return hashes


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
        step = 0
        plan = SyncPlan()

        identity_index: TrackIdentityIndex | None = None
        if self._identity_db_path:
            try:
                identity_index = TrackIdentityIndex(self._identity_db_path)
                identity_index.open()
            except Exception:
                identity_index = None

        source_track_keys: set[tuple[str, str, str, int, int]] = set()
        source_track_uids: set[str] = set()
        dest_track_uids: set[str] = set()

        source_identity_set: set[tuple[str, str, str]] = set()
        dest_identity_set: set[tuple[str, str, str]] = set()

        source_track_uid_by_path: dict[Path, str] = {}
        dest_track_uid_by_path: dict[Path, str] = {}
        source_identity_candidates_by_path: dict[Path, set[tuple[str, str, str]]] = {}
        dest_identity_candidates_by_path: dict[Path, set[tuple[str, str, str]]] = {}

        source_dir_keys: dict[Path, set[tuple[str, str]]] = {}
        dest_dir_keys: dict[Path, set[tuple[str, str]]] = {}

        source_audio_by_path: dict[Path, AudioFile] = {}
        dest_audio_by_path: dict[Path, AudioFile] = {}
        source_tag_cache: dict[Path, dict] = {}
        dest_tag_cache: dict[Path, dict] = {}

        source_files_by_size_ext: dict[tuple[int, str], list[Path]] = {}
        dest_files_by_size_ext: dict[tuple[int, str], list[Path]] = {}
        source_hashes_by_size_ext: dict[tuple[int, str], set[str]] = {}
        dest_hashes_by_size_ext: dict[tuple[int, str], set[str]] = {}
        source_hash_buckets_loaded: set[tuple[int, str]] = set()
        dest_hash_buckets_loaded: set[tuple[int, str]] = set()
        source_hash_cache: dict[Path, str] = {}
        dest_hash_cache: dict[Path, str] = {}

        try:
            # Pre-scan destination tree: collect identity/hash signals.
            for af in dest_files:
                dest_audio_by_path[af.path] = af
                bucket = (af.size, af.extension)
                dest_files_by_size_ext.setdefault(bucket, []).append(af.path)

                candidates = _identity_candidates(af.path, {})
                dest_tags: dict = {}
                record = None

                if identity_index is not None:
                    try:
                        record = identity_index.get(af.path, af.mtime_ns, af.size)
                    except Exception:
                        record = None

                if record is not None:
                    if record.track_uid:
                        dest_track_uids.add(record.track_uid)
                        dest_track_uid_by_path[af.path] = record.track_uid
                    if record.content_sha1:
                        dest_hashes_by_size_ext.setdefault(bucket, set()).add(record.content_sha1)
                    candidates.update(_identity_candidates_from_loose_key(record.loose_identity_key))
                else:
                    try:
                        dest_tags = self._tag_manager.read(af.path).as_dict()
                    except Exception:
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
                        except Exception:
                            record = None
                        if record is not None:
                            if record.track_uid:
                                dest_track_uids.add(record.track_uid)
                                dest_track_uid_by_path[af.path] = record.track_uid
                            if record.content_sha1:
                                dest_hashes_by_size_ext.setdefault(bucket, set()).add(record.content_sha1)
                            candidates.update(_identity_candidates_from_loose_key(record.loose_identity_key))

                dest_tag_cache[af.path] = dest_tags
                dest_identity_candidates_by_path[af.path] = candidates
                dest_identity_set.update(candidates)

            # Source pass: decide whether each item is pending vs already exists.
            for af in source_files:
                source_audio_by_path[af.path] = af
                bucket = (af.size, af.extension)
                source_files_by_size_ext.setdefault(bucket, []).append(af.path)

                if self._cancelled:
                    break

                step += 1
                if progress_cb:
                    progress_cb(step, total_steps or 1, af.path.name)

                try:
                    source_tags = self._tag_manager.read(af.path).as_dict()
                except Exception:
                    source_tags = {}
                source_tag_cache[af.path] = source_tags

                source_track_keys.add(_track_identity(af.path, source_tags))

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
                    except Exception:
                        record = None
                    if record is not None:
                        source_uid = record.track_uid
                        if record.content_sha1:
                            source_hashes_by_size_ext.setdefault(bucket, set()).add(record.content_sha1)
                        source_candidates.update(_identity_candidates_from_loose_key(record.loose_identity_key))

                if source_uid:
                    source_track_uids.add(source_uid)
                    source_track_uid_by_path[af.path] = source_uid

                source_identity_candidates_by_path[af.path] = source_candidates
                source_identity_set.update(source_candidates)

                dest_path = _build_dest_path(dest_dir, source_tags, af.extension, self._path_format, af.path)
                item = SyncItem(source=af.path, dest=dest_path)

                if _path_exists_or_equivalent(dest_path, dest_dir_keys):
                    item.status = "exists"
                elif source_uid and source_uid in dest_track_uids:
                    item.status = "exists"
                elif source_candidates & dest_identity_set:
                    item.status = "exists"
                else:
                    source_sha = _get_or_compute_sha1(
                        af.path,
                        af=af,
                        tags=source_tags,
                        hash_cache=source_hash_cache,
                        identity_index=identity_index,
                    )
                    if source_sha:
                        dest_hashes = _ensure_hash_bucket(
                            bucket,
                            dest_files_by_size_ext,
                            dest_audio_by_path,
                            dest_tag_cache,
                            dest_hash_cache,
                            dest_hashes_by_size_ext,
                            dest_hash_buckets_loaded,
                            identity_index,
                        )
                        if source_sha in dest_hashes:
                            item.status = "exists"
                plan.items.append(item)

            if include_reverse and not self._cancelled:
                for af in dest_files:
                    if self._cancelled:
                        break

                    step += 1
                    if progress_cb:
                        progress_cb(step, total_steps or 1, f"reverse: {af.path.name}")

                    dest_tags = dest_tag_cache.get(af.path, {})
                    track_key = _track_identity(af.path, dest_tags)
                    if track_key in source_track_keys:
                        continue

                    dest_uid = dest_track_uid_by_path.get(af.path, "")
                    if dest_uid and dest_uid in source_track_uids:
                        continue

                    dest_candidates = dest_identity_candidates_by_path.get(
                        af.path,
                        _identity_candidates(af.path, dest_tags),
                    )
                    if dest_candidates & source_identity_set:
                        continue

                    bucket = (af.size, af.extension)
                    dest_sha = _get_or_compute_sha1(
                        af.path,
                        af=af,
                        tags=dest_tags,
                        hash_cache=dest_hash_cache,
                        identity_index=identity_index,
                    )
                    if dest_sha:
                        source_hashes = _ensure_hash_bucket(
                            bucket,
                            source_files_by_size_ext,
                            source_audio_by_path,
                            source_tag_cache,
                            source_hash_cache,
                            source_hashes_by_size_ext,
                            source_hash_buckets_loaded,
                            identity_index,
                        )
                        if dest_sha in source_hashes:
                            continue

                    source_track_keys.add(track_key)
                    source_path = _build_dest_path(source_dir, dest_tags, af.extension, self._path_format, af.path)
                    item = SyncItem(source=af.path, dest=source_path)
                    if _path_exists_or_equivalent(source_path, source_dir_keys):
                        item.status = "exists"
                    plan.items.append(item)

            return plan
        finally:
            if identity_index is not None:
                try:
                    identity_index.close()
                except Exception:
                    pass

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
            except Exception:
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
                            except Exception:
                                tags = {}
                            sha1 = _file_sha1(item.source, source_hash_cache) or ""
                            identity_index.upsert(
                                item.dest,
                                stat.st_mtime_ns,
                                stat.st_size,
                                tags,
                                content_sha1=sha1,
                                use_path_hints=True,
                            )
                        except Exception:
                            pass
                except Exception as e:
                    item.status = "error"
                    item.error = str(e)

            return plan
        finally:
            if identity_index is not None:
                try:
                    identity_index.close()
                except Exception:
                    pass
