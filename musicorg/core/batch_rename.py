"""Helpers for previewing and validating batch file renames."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from musicorg.core.tagger import TagData

_INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
BATCH_RENAME_METADATA_FIELDS: tuple[str, ...] = (
    "title",
    "artist",
    "album",
    "albumartist",
)


@dataclass(frozen=True, slots=True)
class BatchRenameRule:
    """Rename settings supplied by the UI."""

    pattern: str
    replacement: str = ""
    use_regex: bool = False
    case_sensitive: bool = False
    include_extension: bool = False


@dataclass(frozen=True, slots=True)
class RenamePreviewItem:
    """One source -> destination rename preview row."""

    source: Path
    destination: Path


@dataclass(frozen=True, slots=True)
class BatchRenamePreview:
    """Validated rename preview for a selection."""

    items: tuple[RenamePreviewItem, ...]
    planned_items: tuple[RenamePreviewItem, ...]
    unchanged_count: int
    total_count: int


def build_batch_rename_preview(
    paths: Iterable[str | Path],
    rule: BatchRenameRule,
) -> BatchRenamePreview:
    """Build a validated preview for a batch rename operation."""

    ordered_paths = _ordered_unique_paths(paths)
    if not ordered_paths:
        return BatchRenamePreview(items=(), planned_items=(), unchanged_count=0, total_count=0)

    if not rule.pattern:
        raise ValueError("Enter text or a regex pattern to rename files.")

    replacer = compile_batch_rename_replacer(rule)
    final_pairs: list[tuple[Path, Path]] = []
    planned_items: list[RenamePreviewItem] = []
    changed_items: list[RenamePreviewItem] = []
    unchanged_count = 0

    for source_path in ordered_paths:
        original_name = source_path.name if rule.include_extension else source_path.stem
        renamed_name = replacer(original_name)
        destination_name = (
            renamed_name if rule.include_extension else f"{renamed_name}{source_path.suffix}"
        )
        destination_name = _normalize_destination_name(destination_name)
        _validate_destination_name(destination_name, source_path.name)
        destination_path = source_path.with_name(destination_name)
        final_pairs.append((source_path, destination_path))
        planned_item = RenamePreviewItem(source=source_path, destination=destination_path)
        planned_items.append(planned_item)
        if destination_path == source_path:
            unchanged_count += 1
            continue
        changed_items.append(planned_item)

    _validate_final_destinations(final_pairs)
    _validate_existing_destination_conflicts(ordered_paths, changed_items)

    return BatchRenamePreview(
        items=tuple(changed_items),
        planned_items=tuple(planned_items),
        unchanged_count=unchanged_count,
        total_count=len(ordered_paths),
    )


def compile_batch_rename_replacer(rule: BatchRenameRule) -> Callable[[str], str]:
    """Compile a rename rule into a text replacement callable."""

    flags = 0 if rule.case_sensitive else re.IGNORECASE
    if rule.use_regex:
        try:
            pattern = re.compile(rule.pattern, flags)
        except re.error as exc:
            raise ValueError(f"Invalid regex: {exc}") from exc

        def replace(value: str) -> str:
            return pattern.sub(rule.replacement, value)

        return replace

    pattern = re.compile(re.escape(rule.pattern), flags)

    def replace(value: str) -> str:
        return pattern.sub(lambda _match: rule.replacement, value)

    return replace


def apply_batch_rename_to_tags(
    tags: TagData,
    rule: BatchRenameRule,
    fields: Iterable[str],
) -> tuple[TagData, bool]:
    """Apply the same replacement rule to selected text tag fields."""

    normalized_fields = normalize_metadata_fields(fields)
    if not normalized_fields:
        return TagData(**tags.as_dict()), False

    replacer = compile_batch_rename_replacer(rule)
    updated = TagData(**tags.as_dict())
    changed = False
    for field_name in normalized_fields:
        original_value = getattr(updated, field_name)
        replaced_value = replacer(str(original_value))
        if replaced_value != original_value:
            setattr(updated, field_name, replaced_value)
            changed = True
    return updated, changed


def normalize_metadata_fields(fields: Iterable[str]) -> tuple[str, ...]:
    """Validate and deduplicate supported metadata fields."""

    normalized: list[str] = []
    seen: set[str] = set()
    for field in fields:
        name = str(field).strip()
        if not name or name in seen:
            continue
        if name not in BATCH_RENAME_METADATA_FIELDS:
            raise ValueError(f"Unsupported metadata field: {name}")
        seen.add(name)
        normalized.append(name)
    return tuple(normalized)


def _ordered_unique_paths(paths: Iterable[str | Path]) -> list[Path]:
    ordered: list[Path] = []
    seen: set[str] = set()
    for raw_path in paths:
        path = Path(raw_path)
        key = _path_key(path)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path)
    return ordered


def _normalize_destination_name(destination_name: str) -> str:
    normalized = destination_name.strip()
    if not normalized:
        return normalized
    if normalized.startswith(".") or "." not in normalized:
        return normalized
    stem, suffix = normalized.rsplit(".", 1)
    return f"{stem.rstrip()}.{suffix.lstrip()}"


def _validate_destination_name(destination_name: str, source_name: str) -> None:
    if not destination_name:
        raise ValueError(f"Rename would produce an empty filename for {source_name}.")
    if destination_name in {".", ".."}:
        raise ValueError(f"Rename would produce an invalid filename for {source_name}.")
    if _INVALID_FILENAME_CHARS_RE.search(destination_name):
        raise ValueError(f"Rename would produce illegal characters in {destination_name}.")
    if destination_name[-1] in {" ", "."}:
        raise ValueError(
            f"Rename would produce a filename ending with a space or period: {destination_name}."
        )

    stem = Path(destination_name).stem.upper()
    if stem in _WINDOWS_RESERVED_NAMES:
        raise ValueError(f"Rename would produce a reserved Windows name: {destination_name}.")


def _validate_final_destinations(final_pairs: list[tuple[Path, Path]]) -> None:
    destinations: dict[str, Path] = {}
    for source_path, destination_path in final_pairs:
        key = _path_key(destination_path)
        existing = destinations.get(key)
        if existing is not None and existing != source_path:
            raise ValueError(
                "Rename would create duplicate filenames: "
                f"{existing.name} and {source_path.name} both become {destination_path.name}."
            )
        destinations[key] = source_path


def _validate_existing_destination_conflicts(
    source_paths: list[Path],
    changed_items: list[RenamePreviewItem],
) -> None:
    source_keys = {_path_key(path) for path in source_paths}
    for item in changed_items:
        destination_key = _path_key(item.destination)
        if destination_key in source_keys:
            continue
        if item.destination.exists():
            raise ValueError(
                f"Destination already exists on disk: {item.destination.name}."
            )


def _path_key(path: Path) -> str:
    return str(path).casefold()
