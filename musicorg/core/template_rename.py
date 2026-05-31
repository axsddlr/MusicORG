"""Template-based file rename using tag variables ($artist, $title, etc.)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from musicorg.core.tagger import TagManager

_TAG_VAR_RE = re.compile(r"\$(artist|title|album|albumartist|track|disc|year|genre)")


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

    invalid_vars = set(_TAG_VAR_RE.findall(template)) - {
        "artist", "title", "album", "albumartist", "track", "disc", "year", "genre"
    }
    if invalid_vars:
        raise ValueError(f"Unknown variables: {', '.join(sorted(invalid_vars))}")

    tm = TagManager()
    items: list[TemplateRenameItem] = []

    for path in paths:
        try:
            tags = tm.read(path)
        except Exception:
            continue

        dest = template
        replacements: dict[str, str] = {
            "artist": tags.artist or "",
            "title": tags.title or "",
            "album": tags.album or "",
            "albumartist": tags.albumartist or "",
            "year": str(tags.year) if tags.year else "",
            "genre": tags.genre or "",
        }
        replacements["track"] = f"{tags.track:02d}" if tags.track else ""
        replacements["disc"] = f"{tags.disc:02d}" if tags.disc else ""

        dest = re.sub(r"\$artist", _escape_path(replacements["artist"]), dest)
        dest = re.sub(r"\$title", _escape_path(replacements["title"]), dest)
        dest = re.sub(r"\$album", _escape_path(replacements["album"]), dest)
        dest = re.sub(r"\$albumartist", _escape_path(replacements["albumartist"]), dest)
        dest = re.sub(r"\$track", _escape_path(replacements["track"]), dest)
        dest = re.sub(r"\$disc", _escape_path(replacements["disc"]), dest)
        dest = re.sub(r"\$year", _escape_path(replacements["year"]), dest)
        dest = re.sub(r"\$genre", _escape_path(replacements["genre"]), dest)

        if sanitize:
            dest = _sanitize_filename(dest)

        dest_path = path.parent / dest
        if dest_path != path and dest_path.name:
            items.append(
                TemplateRenameItem(
                    source=path,
                    destination=dest_path,
                    new_name=dest_path.name,
                )
            )

    return items


def _escape_path(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", value)


def _sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"_{2,}", "_", name)
    name = name.strip(". ")
    return name if name else "unknown"
