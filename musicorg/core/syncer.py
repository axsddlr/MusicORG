"""Non-destructive sync: copy files from source to destination using tag-based structure."""

from __future__ import annotations

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
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Remove leading/trailing dots and spaces
    name = name.strip('. ')
    return name or "_"


def _build_dest_path(dest_root: Path, tags: dict, ext: str,
                     path_format: str) -> Path:
    """Build destination path from tags and format string."""
    artist = tags.get("albumartist") or tags.get("artist") or "Unknown Artist"
    album = tags.get("album") or "Unknown Album"
    track = tags.get("track", 0)
    title = tags.get("title") or "Unknown Title"
    year = tags.get("year", 0)

    # Build from format string by substituting variables
    path_str = path_format
    path_str = path_str.replace("$albumartist", artist)
    path_str = path_str.replace("$artist", artist)
    path_str = path_str.replace("$album", album)
    disc = tags.get("disc", 0)
    path_str = path_str.replace("$disc0", f"{disc:02d}" if disc else "01")
    path_str = path_str.replace("$disc", str(disc) if disc else "1")
    path_str = path_str.replace("$track", f"{track:02d}" if track else "00")
    path_str = path_str.replace("$title", title)
    path_str = path_str.replace("$year", str(year) if year else "0000")

    # Split into directory parts and filename, sanitize each
    parts = path_str.replace("\\", "/").split("/")
    sanitized = [_sanitize_filename(p) for p in parts]

    # Last part is filename, add extension
    sanitized[-1] = sanitized[-1] + ext

    return dest_root.joinpath(*sanitized)


def _normalize_track_value(value: str) -> str:
    return " ".join(value.strip().lower().split())


_LEADING_TRACK_PREFIX_RE = re.compile(
    r"^\s*(?:(?:(?:#|\d{1,3})\s*[-–—_.]\s*)*(?:#|\d{1,3}))\s*(?:[-–—_.]\s*)?"
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


class SyncManager:
    """Plans and executes non-destructive file copy operations."""

    def __init__(self, path_format: str = "$albumartist/$album/$track $title") -> None:
        self._path_format = path_format
        self._tag_manager = TagManager()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def plan_sync(self, source_dir: str | Path, dest_dir: str | Path,
                  progress_cb: Callable[[int, int, str], None] | None = None,
                  include_reverse: bool = False) -> SyncPlan:
        """Build sync plan, optionally including reverse (dest->source) by track identity."""
        source_dir = Path(source_dir)
        dest_dir = Path(dest_dir)

        source_files = FileScanner(source_dir).scan()
        dest_files = FileScanner(dest_dir).scan() if include_reverse else []
        total_steps = len(source_files) + len(dest_files)
        step = 0
        plan = SyncPlan()
        source_track_keys: set[tuple[str, str, str, int, int]] = set()
        dest_dir_keys: dict[Path, set[tuple[str, str]]] = {}
        source_dir_keys: dict[Path, set[tuple[str, str]]] = {}

        for af in source_files:
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

            dest_path = _build_dest_path(dest_dir, tag_dict, af.extension,
                                         self._path_format)

            item = SyncItem(source=af.path, dest=dest_path)
            if _path_exists_or_equivalent(dest_path, dest_dir_keys):
                item.status = "exists"
            plan.items.append(item)

        if include_reverse and not self._cancelled:
            for af in dest_files:
                if self._cancelled:
                    break

                step += 1
                if progress_cb:
                    progress_cb(step, total_steps or 1, f"reverse: {af.path.name}")

                try:
                    tags = self._tag_manager.read(af.path)
                    tag_dict = tags.as_dict()
                except Exception:
                    tag_dict = {}

                key = _track_identity(af.path, tag_dict)
                if key in source_track_keys:
                    continue
                source_track_keys.add(key)

                source_path = _build_dest_path(source_dir, tag_dict, af.extension,
                                               self._path_format)

                item = SyncItem(source=af.path, dest=source_path)
                if _path_exists_or_equivalent(source_path, source_dir_keys):
                    item.status = "exists"
                plan.items.append(item)

        return plan

    def execute_sync(self, plan: SyncPlan,
                     progress_cb: Callable[[int, int, str], None] | None = None
                     ) -> SyncPlan:
        """Execute the copy operations in the plan."""
        self._cancelled = False
        pending = [item for item in plan.items if item.status == "pending"]

        for i, item in enumerate(pending):
            if self._cancelled:
                break

            if progress_cb:
                progress_cb(i + 1, len(pending), item.source.name)

            try:
                item.dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(item.source), str(item.dest))
                item.status = "copied"
            except Exception as e:
                item.status = "error"
                item.error = str(e)

        return plan
