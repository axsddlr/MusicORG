"""Find duplicate audio files by tag metadata and exact content."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from musicorg.core.tagger import TagData

DuplicateMatchMode = Literal["strict", "aggressive"]

FORMAT_PRIORITY: dict[str, int] = {
    ".flac": 2,
    ".mp3": 1,
}

_LEADING_TRACK_PREFIX_RE = re.compile(
    r"^\s*(?:(?:(?:#|\d{1,3})\s*(?:[-_.]|\u2013|\u2014)\s*)*(?:#|\d{1,3}))\s*(?:(?:[-_.]|\u2013|\u2014)\s*)?"
)


def normalize_title(title: str) -> str:
    """Lowercase, strip, and collapse whitespace."""
    return re.sub(r"\s+", " ", title.strip().lower())


def _normalize_identity_component(value: str) -> str:
    """Normalize punctuation and spacing for flexible matching."""
    cleaned = re.sub(r"[^\w]+", " ", value.lower().replace("_", " "))
    return " ".join(cleaned.split())


def _path_hints(path: Path) -> tuple[str, str]:
    """Best-effort (artist, album) from path segments."""
    album = ""
    artist = ""
    parent = path.parent
    if parent != path:
        album = parent.name
        grandparent = parent.parent
        if grandparent != parent:
            artist = grandparent.name
    return artist, album


def _normalized_filename_title(path: Path) -> str:
    stem = path.stem
    stripped = _LEADING_TRACK_PREFIX_RE.sub("", stem, count=1)
    title = _normalize_identity_component(stripped)
    if title:
        return title
    return _normalize_identity_component(stem)


def _metadata_group_key(path: Path, tags: TagData, *, match_artist: bool) -> str:
    title = _normalize_identity_component(tags.title) or _normalized_filename_title(path)
    if not title:
        return ""

    path_artist, path_album = _path_hints(path)
    album = _normalize_identity_component(tags.album) or _normalize_identity_component(path_album)
    if match_artist:
        artist = _normalize_identity_component(tags.artist) or _normalize_identity_component(path_artist)
        return f"{title} || {album} || {artist}"
    return f"{title} || {album}"


def _strict_metadata_group_key(tags: TagData, *, match_artist: bool) -> str:
    """Legacy tag-only duplicate key."""
    title = normalize_title(tags.title)
    if not title:
        return ""
    album = normalize_title(tags.album)
    if match_artist:
        artist = normalize_title(tags.artist)
        return f"{title} || {album} || {artist}"
    return f"{title} || {album}"


def _normalize_match_mode(mode: str) -> DuplicateMatchMode:
    normalized = mode.strip().lower()
    if normalized == "strict":
        return "strict"
    return "aggressive"


def _file_sha1(path: Path, cache: dict[Path, str]) -> str | None:
    cached = cache.get(path)
    if cached is not None:
        return cached
    try:
        digest = hashlib.sha1(usedforsecurity=False)
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return None
    value = digest.hexdigest()
    cache[path] = value
    return value


def _find(parent: list[int], idx: int) -> int:
    while parent[idx] != idx:
        parent[idx] = parent[parent[idx]]
        idx = parent[idx]
    return idx


def _union(parent: list[int], rank: list[int], a: int, b: int) -> None:
    ra = _find(parent, a)
    rb = _find(parent, b)
    if ra == rb:
        return
    if rank[ra] < rank[rb]:
        parent[ra] = rb
    elif rank[ra] > rank[rb]:
        parent[rb] = ra
    else:
        parent[rb] = ra
        rank[ra] += 1


@dataclass
class DuplicateFile:
    """One file within a duplicate group."""

    path: Path
    tags: TagData
    extension: str
    size: int
    bitrate: int = 0
    keep: bool = False


@dataclass
class DuplicateGroup:
    """A set of files sharing the same normalized identity or exact content."""

    normalized_key: str
    files: list[DuplicateFile] = field(default_factory=list)

    @property
    def kept_file(self) -> DuplicateFile | None:
        for f in self.files:
            if f.keep:
                return f
        return None

    @property
    def deletable_files(self) -> list[DuplicateFile]:
        return [f for f in self.files if not f.keep]


def find_duplicates(
    file_tags: list[tuple[Path, TagData, int]],
    *,
    match_artist: bool = False,
    mode: str = "aggressive",
) -> list[DuplicateGroup]:
    """Find duplicate audio files by metadata identity and exact content hash.

    Args:
        file_tags: List of (path, TagData, file_size) tuples.
        match_artist: If True, group by (title + album + artist) identity.
        mode: Matching mode: "strict" (tags only) or "aggressive" (tags + path + hash).

    Returns:
        List of DuplicateGroup, each containing 2+ files considered duplicates.
    """
    normalized_mode = _normalize_match_mode(mode)

    files: list[DuplicateFile] = []
    metadata_keys: list[str] = []
    metadata_groups: dict[str, list[int]] = {}
    size_groups: dict[int, list[int]] = {}

    for path, tags, size in file_tags:
        ext = path.suffix.lower()
        bitrate = getattr(tags, "bitrate", 0) or 0
        df = DuplicateFile(path=path, tags=tags, extension=ext, size=size, bitrate=bitrate)
        idx = len(files)
        files.append(df)

        if normalized_mode == "strict":
            key = _strict_metadata_group_key(tags, match_artist=match_artist)
        else:
            key = _metadata_group_key(path, tags, match_artist=match_artist)

        metadata_keys.append(key)
        if key:
            metadata_groups.setdefault(key, []).append(idx)
        if normalized_mode == "aggressive":
            size_groups.setdefault(size, []).append(idx)

    if len(files) < 2:
        return []

    parent = list(range(len(files)))
    rank = [0] * len(files)

    for indices in metadata_groups.values():
        if len(indices) < 2:
            continue
        leader = indices[0]
        for idx in indices[1:]:
            _union(parent, rank, leader, idx)

    hash_cache: dict[Path, str] = {}
    index_hash: dict[int, str] = {}
    if normalized_mode == "aggressive":
        for indices in size_groups.values():
            if len(indices) < 2:
                continue
            hash_groups: dict[str, list[int]] = {}
            for idx in indices:
                digest = _file_sha1(files[idx].path, hash_cache)
                if not digest:
                    continue
                index_hash[idx] = digest
                hash_groups.setdefault(digest, []).append(idx)
            for same_hash_indices in hash_groups.values():
                if len(same_hash_indices) < 2:
                    continue
                leader = same_hash_indices[0]
                for idx in same_hash_indices[1:]:
                    _union(parent, rank, leader, idx)

    components: dict[int, list[int]] = {}
    for idx in range(len(files)):
        root = _find(parent, idx)
        components.setdefault(root, []).append(idx)

    result: list[DuplicateGroup] = []
    for members in components.values():
        if len(members) < 2:
            continue

        component_files = [files[idx] for idx in members]
        component_files.sort(
            key=lambda f: (FORMAT_PRIORITY.get(f.extension, 0), f.bitrate, f.size),
            reverse=True,
        )
        component_files[0].keep = True
        for f in component_files[1:]:
            f.keep = False

        component_keys = sorted({metadata_keys[idx] for idx in members if metadata_keys[idx]})
        if component_keys:
            group_key = component_keys[0]
        else:
            component_hashes = sorted({index_hash[idx] for idx in members if idx in index_hash})
            if component_hashes:
                group_key = f"hash:{component_hashes[0][:12]}"
            else:
                group_key = "unknown"

        result.append(DuplicateGroup(normalized_key=group_key, files=component_files))

    result.sort(key=lambda g: g.normalized_key)
    return result
