"""Non-destructive sync: copy files from source to destination using tag-based structure."""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from musicorg.core.scanner import FileScanner
from musicorg.core.tagger import TagManager


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


def _has_exact_content_match(
    source_path: Path,
    source_size: int,
    source_extension: str,
    destination_files_by_size_ext: dict[tuple[int, str], list[Path]],
    source_hash_cache: dict[Path, str],
    destination_hash_cache: dict[Path, str],
) -> bool:
    """Return True if any destination file has identical bytes."""
    candidates = destination_files_by_size_ext.get((source_size, source_extension), [])
    if not candidates:
        return False
    source_hash = _file_sha1(source_path, source_hash_cache)
    if source_hash is None:
        return False
    for destination_path in candidates:
        destination_hash = _file_sha1(destination_path, destination_hash_cache)
        if destination_hash is None:
            continue
        if source_hash == destination_hash:
            return True
    return False


class SyncManager:
    """Plans and executes non-destructive file copy operations."""

    def __init__(self, path_format: str = "$albumartist/$album/$track $title") -> None:
        self._path_format = path_format
        self._tag_manager = TagManager()
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
        source_track_keys: set[tuple[str, str, str, int, int]] = set()
        source_identity_set: set[tuple[str, str, str]] = set()
        dest_dir_keys: dict[Path, set[tuple[str, str]]] = {}
        source_dir_keys: dict[Path, set[tuple[str, str]]] = {}

        # Pre-scan destination to build identity and content lookup indexes.
        dest_tag_cache: dict[Path, dict] = {}
        dest_identity_set: set[tuple[str, str, str]] = set()
        dest_files_by_size_ext: dict[tuple[int, str], list[Path]] = {}
        source_files_by_size_ext: dict[tuple[int, str], list[Path]] = {}
        source_hash_cache: dict[Path, str] = {}
        dest_hash_cache: dict[Path, str] = {}

        for af in dest_files:
            dest_files_by_size_ext.setdefault((af.size, af.extension), []).append(af.path)
            try:
                tags = self._tag_manager.read(af.path)
                tag_dict = tags.as_dict()
            except Exception:
                tag_dict = {}
            dest_tag_cache[af.path] = tag_dict
            dest_identity_set.update(_identity_candidates(af.path, tag_dict))

        for af in source_files:
            source_files_by_size_ext.setdefault((af.size, af.extension), []).append(af.path)
            if self._cancelled:
                break

            step += 1
            if progress_cb:
                progress_cb(step, total_steps or 1, af.path.name)

            try:
                tags = self._tag_manager.read(af.path)
                tag_dict = tags.as_dict()
            except Exception:
                tag_dict = {}

            source_track_keys.add(_track_identity(af.path, tag_dict))
            source_identity_candidates = _identity_candidates(af.path, tag_dict)
            source_identity_set.update(source_identity_candidates)

            dest_path = _build_dest_path(dest_dir, tag_dict, af.extension, self._path_format, af.path)
            item = SyncItem(source=af.path, dest=dest_path)

            if _path_exists_or_equivalent(dest_path, dest_dir_keys):
                item.status = "exists"
            elif source_identity_candidates & dest_identity_set:
                item.status = "exists"
            elif _has_exact_content_match(
                af.path,
                af.size,
                af.extension,
                dest_files_by_size_ext,
                source_hash_cache,
                dest_hash_cache,
            ):
                item.status = "exists"
            plan.items.append(item)

        if include_reverse and not self._cancelled:
            for af in dest_files:
                if self._cancelled:
                    break

                step += 1
                if progress_cb:
                    progress_cb(step, total_steps or 1, f"reverse: {af.path.name}")

                # Reuse cached tags from pre-scan pass.
                tag_dict = dest_tag_cache.get(af.path, {})

                key = _track_identity(af.path, tag_dict)
                if key in source_track_keys:
                    continue
                dest_identity_candidates = _identity_candidates(af.path, tag_dict)
                if dest_identity_candidates & source_identity_set:
                    continue
                if _has_exact_content_match(
                    af.path,
                    af.size,
                    af.extension,
                    source_files_by_size_ext,
                    dest_hash_cache,
                    source_hash_cache,
                ):
                    continue
                source_track_keys.add(key)

                source_path = _build_dest_path(source_dir, tag_dict, af.extension, self._path_format, af.path)
                item = SyncItem(source=af.path, dest=source_path)
                if _path_exists_or_equivalent(source_path, source_dir_keys):
                    item.status = "exists"
                plan.items.append(item)

        return plan

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
            except Exception as e:
                item.status = "error"
                item.error = str(e)

        return plan

