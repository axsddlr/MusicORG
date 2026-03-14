"""Shared text normalization utilities for audio metadata matching."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Matches leading track-number prefixes like "01 - ", "#3 - ", "1.2.", etc.
LEADING_TRACK_PREFIX_RE = re.compile(
    r"^\s*(?:(?:(?:#|\d{1,3})\s*(?:[-_.]|\u2013|\u2014)\s*)*(?:#|\d{1,3}))\s*(?:(?:[-_.]|\u2013|\u2014)\s*)?"
)


def normalize_loose(value: Any) -> str:
    """Lowercase, strip punctuation, collapse whitespace — for fuzzy matching."""
    cleaned = re.sub(r"[^\w]+", " ", str(value or "").lower().replace("_", " "))
    return " ".join(cleaned.split())


def path_artist_album_hints(path: Path) -> tuple[str, str]:
    """Best-effort (artist, album) from grandparent/parent directory names."""
    parent = path.parent
    album = parent.name if parent != path else ""
    grandparent = parent.parent
    artist = grandparent.name if grandparent != parent else ""
    return artist, album
