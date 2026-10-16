"""Parse tag hints out of a filename using a ``$var`` template (reverse of template_rename)."""
from __future__ import annotations

import re
from pathlib import Path

from musicorg.core.template_rename import _VAR_RE, _VARS

_NUMERIC = {"track", "disc", "year"}
_NUM_KEYS = {"track", "disc"}

DEFAULT_TEMPLATES = ["$track - $artist - $title", "$artist - $title", "$track. $title", "$track $title"]


def _compile(template: str) -> re.Pattern:
    if not template.strip():
        raise ValueError("Template is empty")
    names = _VAR_RE.findall(template)
    for n in names:
        if n not in _VARS:
            raise ValueError(f"Unknown template variable: ${n}")
    for n in set(names):
        if names.count(n) > 1:
            raise ValueError(f"Duplicate template variable: ${n}")
    parts, pos = [], 0
    for m in _VAR_RE.finditer(template):
        parts.append(re.escape(template[pos:m.start()]))
        n = m.group(1)
        group = r"\d+" if n in _NUMERIC else ".+?"
        parts.append(f"(?P<{n}>{group})")
        pos = m.end()
    parts.append(re.escape(template[pos:]))
    return re.compile("^" + "".join(parts) + "$")


def parse_filename(path: str | Path, template: str) -> dict[str, str] | None:
    pattern = _compile(template)
    stem = Path(path).stem
    if "_" not in template:
        stem = stem.replace("_", " ")
    m = pattern.match(stem)
    if not m:
        return None
    out = {}
    for k, v in m.groupdict().items():
        v = v.strip()
        if k in _NUM_KEYS:
            v = v.lstrip("0") or "0"
        if v:
            out[k] = v
    return out


def guess_from_filename(path: str | Path) -> dict[str, str] | None:
    for t in DEFAULT_TEMPLATES:
        r = parse_filename(path, t)
        if r:
            return r
    return None
