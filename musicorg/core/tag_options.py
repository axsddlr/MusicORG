"""Pure helpers for key notation and genre cleanup."""

from __future__ import annotations

import re

_NOTE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_KEY_RE = re.compile(
    r"^([A-G])\s*([#b\u266f\u266d]?)\s*(m|min|minor|maj|major)?$", re.IGNORECASE
)
_CAMELOT_RE = re.compile(r"^(\d{1,2})([ab])$", re.IGNORECASE)
_OPEN_RE = re.compile(r"^(\d{1,2})([md])$", re.IGNORECASE)


def _parse(key: str) -> tuple[int, int] | None:
    """Return (fifths_index 0..11 from C-major ordering, 1 if major else 0).

    The index is for the *major* key at the same position (relative major
    for minor keys), so Camelot/Open Key numbers share one formula.
    """
    if not isinstance(key, str):
        return None
    s = key.strip()
    if m := _CAMELOT_RE.match(s):
        num, major = int(m[1]), m[2].lower() == "b"
        return ((num - 8) % 12, int(major)) if 1 <= num <= 12 else None
    if m := _OPEN_RE.match(s):
        num, major = int(m[1]), m[2].lower() == "d"
        return ((num - 1) % 12, int(major)) if 1 <= num <= 12 else None
    m = _KEY_RE.match(s)
    if not m:
        return None
    pc = _NOTE_PC[m[1].upper()]
    if m[2] in ("#", "\u266f"):
        pc += 1
    elif m[2] in ("b", "\u266d"):
        pc -= 1
    mode = (m[3] or "maj").lower()
    major = mode.startswith("maj") or mode == ""
    if not major:
        pc += 3  # relative major
    return (pc * 7) % 12, int(major)


def to_camelot(key: str) -> str | None:
    """Convert a key spelling (or Open Key) to Camelot, e.g. 'Am' -> '8A'."""
    p = _parse(key)
    if p is None:
        return None
    pos, major = p
    return f"{(pos + 7) % 12 + 1}{'B' if major else 'A'}"


def to_open_key(key: str) -> str | None:
    """Convert a key spelling (or Camelot) to Open Key, e.g. 'Am' -> '1m'."""
    p = _parse(key)
    if p is None:
        return None
    pos, major = p
    return f"{pos + 1}{'d' if major else 'm'}"


def key_from_pitch_class(pitch: int, mode: int) -> str | None:
    """Spotify pitch class (0=C..11=B) and mode (1 major, 0 minor) -> 'F#m'/'F#'."""
    if pitch not in range(12) or mode not in (0, 1):
        return None
    return _SHARP_NAMES[pitch] + ("" if mode else "m")


def merge_genres(existing: str, new: str, separator: str = "; ") -> str:
    """Merge two genre strings (split on ; , /), deduping case-insensitively."""
    seen: dict[str, str] = {}
    for g in re.split(r"[;,/]", f"{existing or ''};{new or ''}"):
        g = g.strip()
        if g:
            seen.setdefault(g.casefold(), g)
    return separator.join(seen.values())


_LOWER_JOINS = {"and", "n", "of", "the"}


def capitalize_genre(genre: str) -> str:
    """Title-case words; tokens with any uppercase beyond the first letter
    (EDM, UK, DnB) are kept as-is; 'and'/'n'/'of'/'the' stay lowercase
    except as the first word.
    """
    out = []
    for i, w in enumerate(genre.split()):
        if any(c.isupper() for c in w[1:]) or (len(w) > 1 and w.isupper()):
            out.append(w)
        elif w.lower() in _LOWER_JOINS and i > 0:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:].lower())
    return " ".join(out)
