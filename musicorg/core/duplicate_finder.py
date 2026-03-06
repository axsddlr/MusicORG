"""Find duplicate audio files by metadata and exact content with confidence signals."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from musicorg.core.tagger import TagData

DuplicateMatchMode = Literal["strict", "aggressive"]
MatchReason = Literal["exact_hash", "tag_identity", "filename_path", "unknown"]

FORMAT_PRIORITY: dict[str, int] = {
    ".flac": 2,
    ".mp3": 1,
}

_REASON_CONFIDENCE: dict[MatchReason, float] = {
    "exact_hash": 1.0,
    "tag_identity": 0.9,
    "filename_path": 0.6,
    "unknown": 0.0,
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


def _metadata_group_data(
    path: Path,
    tags: TagData,
    *,
    match_artist: bool,
    mode: DuplicateMatchMode,
) -> tuple[str, MatchReason]:
    if mode == "strict":
        title = normalize_title(tags.title)
        if not title:
            return "", "unknown"
        album = normalize_title(tags.album)
        if match_artist:
            artist = normalize_title(tags.artist)
            return f"{title} || {album} || {artist}", "tag_identity"
        return f"{title} || {album}", "tag_identity"

    title_tag = _normalize_identity_component(tags.title)
    title_path = _normalized_filename_title(path)
    title = title_tag or title_path
    if not title:
        return "", "unknown"

    path_artist, path_album = _path_hints(path)
    album_tag = _normalize_identity_component(tags.album)
    album_path = _normalize_identity_component(path_album)
    album = album_tag or album_path

    if match_artist:
        artist_tag = _normalize_identity_component(tags.artist)
        artist_path = _normalize_identity_component(path_artist)
        artist = artist_tag or artist_path
        key = f"{title} || {album} || {artist}"
        has_strict_tag_identity = bool(title_tag and album_tag and artist_tag)
    else:
        key = f"{title} || {album}"
        has_strict_tag_identity = bool(title_tag and album_tag)

    reason: MatchReason = "tag_identity" if has_strict_tag_identity else "filename_path"
    return key, reason


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


def _reason_confidence(reason: MatchReason) -> float:
    return _REASON_CONFIDENCE.get(reason, 0.0)


def _prefer_reason(current: MatchReason, candidate: MatchReason) -> MatchReason:
    if _reason_confidence(candidate) > _reason_confidence(current):
        return candidate
    return current


@dataclass
class DuplicateFile:
    """One file within a duplicate group."""

    path: Path
    tags: TagData
    extension: str
    size: int
    bitrate: int = 0
    keep: bool = False
    match_reason: MatchReason = "unknown"
    confidence: float = 0.0


@dataclass
class DuplicateGroup:
    """A set of files sharing the same normalized identity or exact content."""

    normalized_key: str
    files: list[DuplicateFile] = field(default_factory=list)
    match_reason: MatchReason = "unknown"
    confidence: float = 0.0

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
    track_uids: dict[Path, str] | None = None,
) -> list[DuplicateGroup]:
    """Find duplicate audio files by metadata identity and exact content hash.

    Args:
        file_tags: List of (path, TagData, file_size) tuples.
        match_artist: If True, group by (title + album + artist) identity.
        mode: Matching mode: "strict" (tags only) or "aggressive" (tags + path + hash).
        track_uids: Optional stable IDs from persistent identity index.

    Returns:
        List of DuplicateGroup, each containing 2+ files considered duplicates.
    """
    normalized_mode = _normalize_match_mode(mode)

    files: list[DuplicateFile] = []
    metadata_keys: list[str] = []
    metadata_groups: dict[str, list[int]] = {}
    metadata_reason_by_key: dict[str, MatchReason] = {}
    uid_groups: dict[str, list[int]] = {}
    size_groups: dict[int, list[int]] = {}

    for path, tags, size in file_tags:
        ext = path.suffix.lower()
        bitrate = getattr(tags, "bitrate", 0) or 0
        df = DuplicateFile(path=path, tags=tags, extension=ext, size=size, bitrate=bitrate)
        idx = len(files)
        files.append(df)

        key, reason = _metadata_group_data(
            path,
            tags,
            match_artist=match_artist,
            mode=normalized_mode,
        )
        metadata_keys.append(key)
        if key:
            metadata_groups.setdefault(key, []).append(idx)
            metadata_reason_by_key[key] = _prefer_reason(
                metadata_reason_by_key.get(key, "unknown"),
                reason,
            )

        if normalized_mode == "aggressive":
            size_groups.setdefault(size, []).append(idx)

        uid = (track_uids or {}).get(path, "")
        if uid:
            uid_groups.setdefault(uid, []).append(idx)

    if len(files) < 2:
        return []

    parent = list(range(len(files)))
    rank = [0] * len(files)
    signal_by_index: dict[int, MatchReason] = {idx: "unknown" for idx in range(len(files))}

    def apply_signal(indices: list[int], reason: MatchReason) -> None:
        for idx in indices:
            signal_by_index[idx] = _prefer_reason(signal_by_index[idx], reason)

    for key, indices in metadata_groups.items():
        if len(indices) < 2:
            continue
        leader = indices[0]
        for idx in indices[1:]:
            _union(parent, rank, leader, idx)
        apply_signal(indices, metadata_reason_by_key.get(key, "unknown"))

    index_hash: dict[int, str] = {}
    for uid, indices in uid_groups.items():
        if len(indices) < 2:
            continue
        leader = indices[0]
        for idx in indices[1:]:
            _union(parent, rank, leader, idx)
        if uid.startswith("sha1:"):
            digest = uid[5:]
            for idx in indices:
                index_hash[idx] = digest
            apply_signal(indices, "exact_hash")
        else:
            apply_signal(indices, "tag_identity")

    hash_cache: dict[Path, str] = {}
    if normalized_mode == "aggressive":
        for indices in size_groups.values():
            if len(indices) < 2:
                continue
            hash_groups: dict[str, list[int]] = {}
            for idx in indices:
                digest = index_hash.get(idx) or _file_sha1(files[idx].path, hash_cache)
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
                apply_signal(same_hash_indices, "exact_hash")

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

        component_reason: MatchReason = "unknown"
        for idx in members:
            component_reason = _prefer_reason(component_reason, signal_by_index.get(idx, "unknown"))
        component_confidence = _reason_confidence(component_reason)

        for f in component_files:
            f.match_reason = component_reason
            f.confidence = component_confidence

        component_keys = sorted({metadata_keys[idx] for idx in members if metadata_keys[idx]})
        if component_keys:
            group_key = component_keys[0]
        else:
            component_hashes = sorted({index_hash[idx] for idx in members if idx in index_hash})
            if component_hashes:
                group_key = f"hash:{component_hashes[0][:12]}"
            else:
                group_key = "unknown"

        result.append(
            DuplicateGroup(
                normalized_key=group_key,
                files=component_files,
                match_reason=component_reason,
                confidence=component_confidence,
            )
        )

    result.sort(key=lambda g: g.normalized_key)
    return result
