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
    path_str = path_str.replace("$track", f"{track:02d}" if track else "00")
    path_str = path_str.replace("$title", title)
    path_str = path_str.replace("$year", str(year) if year else "0000")

    # Split into directory parts and filename, sanitize each
    parts = path_str.replace("\\", "/").split("/")
    sanitized = [_sanitize_filename(p) for p in parts]

    # Last part is filename, add extension
    sanitized[-1] = sanitized[-1] + ext

    return dest_root.joinpath(*sanitized)


class SyncManager:
    """Plans and executes non-destructive file copy operations."""

    def __init__(self, path_format: str = "$albumartist/$album/$track $title") -> None:
        self._path_format = path_format
        self._tag_manager = TagManager()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def plan_sync(self, source_dir: str | Path, dest_dir: str | Path,
                  progress_cb: Callable[[int, int, str], None] | None = None
                  ) -> SyncPlan:
        """Scan source, read tags, compute destination paths, check existence."""
        source_dir = Path(source_dir)
        dest_dir = Path(dest_dir)

        scanner = FileScanner(source_dir)
        files = scanner.scan()
        plan = SyncPlan()

        for i, af in enumerate(files):
            if self._cancelled:
                break

            if progress_cb:
                progress_cb(i + 1, len(files), af.path.name)

            try:
                tags = self._tag_manager.read(af.path)
                tag_dict = tags.as_dict()
            except Exception:
                tag_dict = {}

            dest_path = _build_dest_path(dest_dir, tag_dict, af.extension,
                                         self._path_format)

            item = SyncItem(source=af.path, dest=dest_path)
            if dest_path.exists():
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
