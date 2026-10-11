"""Template-based file rename using tag variables ($artist, $title, etc.)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from musicorg.core.batch_rename import (
    RenamePreviewItem,
    _INVALID_FILENAME_CHARS_RE,
    _normalize_destination_name,
    _validate_destination_name,
    _validate_existing_destination_conflicts,
    _validate_final_destinations,
)
from musicorg.core.tagger import TagManager

_VAR_RE = re.compile(r"\$([A-Za-z]+)")
_VARS = {"artist", "title", "album", "albumartist", "track", "disc", "year", "genre"}


@dataclass
class TemplateRenameItem:
    source: Path
    destination: Path
    new_name: str


def build_template_rename(
    paths: list[Path],
    template: str,
    *,
    sanitize: bool = True,
) -> list[TemplateRenameItem]:
    if not template.strip():
        raise ValueError("Template cannot be empty")

    unknown = sorted(set(_VAR_RE.findall(template)) - _VARS)
    if unknown:
        raise ValueError(f"Unknown variables: {', '.join('$' + v for v in unknown)}")

    tm = TagManager()
    pairs: list[tuple[Path, Path]] = []

    for path in paths:
        try:
            tags = tm.read(path)
        except Exception:
            continue

        values = {
            "artist": tags.artist or "",
            "title": tags.title or "",
            "album": tags.album or "",
            "albumartist": tags.albumartist or "",
            "year": str(tags.year) if tags.year else "",
            "genre": tags.genre or "",
            "track": f"{tags.track:02d}" if tags.track else "",
            "disc": f"{tags.disc:02d}" if tags.disc else "",
        }
        # Function replacement keeps tag values literal (no group-reference expansion).
        dest = _VAR_RE.sub(lambda m: _escape_path(values[m.group(1)]), template)

        if sanitize:
            dest = _sanitize_filename(dest)
        dest = _normalize_destination_name(dest)
        if not dest.lower().endswith(path.suffix.lower()):
            dest += path.suffix
        _validate_destination_name(dest, path.name)
        pairs.append((path, path.parent / dest))

    _validate_final_destinations(pairs)
    items = [
        TemplateRenameItem(source=src, destination=dst, new_name=dst.name)
        for src, dst in pairs
        if dst != src
    ]
    _validate_existing_destination_conflicts(
        [src for src, _ in pairs],
        [RenamePreviewItem(i.source, i.destination) for i in items],
    )
    return items


def _escape_path(value: str) -> str:
    return _INVALID_FILENAME_CHARS_RE.sub("_", value)


def _sanitize_filename(name: str) -> str:
    name = _INVALID_FILENAME_CHARS_RE.sub("_", name)
    name = re.sub(r"_{2,}", "_", name)
    name = name.strip(". ")
    return name if name else "unknown"
