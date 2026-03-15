"""Worker for applying validated file rename plans."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from musicorg.core.batch_rename import (
    BatchRenameRule,
    apply_batch_rename_to_tags,
    normalize_metadata_fields,
)
from musicorg.core.tag_cache import TagCache
from musicorg.core.tagger import TagManager
from musicorg.workers.base_worker import BaseWorker

FileRenameItem = tuple[str | Path, str | Path]
FileRenameFailure = tuple[Path, str]


class FileRenameSummary(TypedDict):
    renamed: int
    total: int
    metadata_updated: int
    metadata_failed: list[FileRenameFailure]


class _RenameCancelled(RuntimeError):
    """Internal sentinel used to rollback on cancellation."""


class FileRenameWorker(BaseWorker):
    """Applies a rename plan in a background thread."""

    def __init__(
        self,
        items: list[FileRenameItem],
        *,
        cache_db_path: str = "",
        metadata_rule: BatchRenameRule | None = None,
        metadata_fields: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self._items = [(Path(source), Path(destination)) for source, destination in items]
        self._cache_db_path = cache_db_path
        self._metadata_rule = metadata_rule
        self._metadata_fields = normalize_metadata_fields(metadata_fields)

    def run(self) -> None:
        self.started.emit()
        total_items = len(self._items)
        if not total_items:
            self.finished.emit(
                self._build_summary(
                    renamed=0,
                    total=0,
                    metadata_updated=0,
                    metadata_failed=[],
                )
            )
            return

        rename_items = [(source, destination) for source, destination in self._items if source != destination]
        metadata_enabled = self._metadata_rule is not None and bool(self._metadata_fields)
        steps_total = (len(rename_items) * 2) + (total_items if metadata_enabled else 0)
        current_paths: dict[Path, Path] = {source: source for source, _ in self._items}
        temp_paths: dict[Path, Path] = {}

        try:
            for index, (source, _destination) in enumerate(rename_items, start=1):
                self._raise_if_cancelled()
                temp_path = self._unique_temp_path(source)
                source.rename(temp_path)
                temp_paths[source] = temp_path
                current_paths[source] = temp_path
                self.progress.emit(index, steps_total, f"Staging {source.name}")

            for index, (source, destination) in enumerate(rename_items, start=1):
                self._raise_if_cancelled()
                temp_paths[source].rename(destination)
                current_paths[source] = destination
                self.progress.emit(
                    len(rename_items) + index,
                    steps_total,
                    f"Renaming to {destination.name}",
                )

            metadata_updated = 0
            metadata_failed: list[FileRenameFailure] = []
            if metadata_enabled and self._metadata_rule is not None:
                tag_manager = TagManager()
                for index, (source, _destination) in enumerate(self._items, start=1):
                    current_path = current_paths[source]
                    try:
                        existing_tags = tag_manager.read(current_path)
                        updated_tags, changed = apply_batch_rename_to_tags(
                            existing_tags,
                            self._metadata_rule,
                            self._metadata_fields,
                        )
                        if changed:
                            tag_manager.write(current_path, updated_tags)
                            metadata_updated += 1
                    except Exception as exc:
                        metadata_failed.append((current_path, str(exc) or exc.__class__.__name__))
                    self.progress.emit(
                        (len(rename_items) * 2) + index,
                        steps_total,
                        f"Updating tags for {current_path.name}",
                    )

            self._invalidate_cache_paths(current_paths)
            self.finished.emit(
                self._build_summary(
                    renamed=len(rename_items),
                    total=total_items,
                    metadata_updated=metadata_updated,
                    metadata_failed=metadata_failed,
                )
            )
        except _RenameCancelled:
            self._rollback(current_paths)
            self.cancelled.emit()
        except Exception as exc:
            rollback_errors = self._rollback(current_paths)
            error_message = str(exc) or exc.__class__.__name__
            if rollback_errors:
                rollback_suffix = "; ".join(rollback_errors)
                error_message = f"{error_message}. Rollback issues: {rollback_suffix}"
            self.error.emit(error_message)

    def _invalidate_cache_paths(self, current_paths: dict[Path, Path]) -> None:
        if not self._cache_db_path:
            return

        cache: TagCache | None = None
        try:
            cache = TagCache(self._cache_db_path)
            cache.open()
            invalidate_paths = [source for source, _ in self._items]
            invalidate_paths.extend(current_paths[source] for source, _ in self._items)
            cache.invalidate_many(invalidate_paths)
        except Exception:
            return
        finally:
            if cache is not None:
                try:
                    cache.close()
                except Exception:
                    pass

    def _rollback(self, current_paths: dict[Path, Path]) -> list[str]:
        rollback_errors: list[str] = []
        for source, _destination in reversed(self._items):
            current = current_paths.get(source, source)
            if current == source:
                continue
            try:
                if current.exists():
                    current.rename(source)
                    current_paths[source] = source
            except Exception as exc:
                rollback_errors.append(f"{current.name} -> {source.name}: {exc}")
        return rollback_errors

    def _raise_if_cancelled(self) -> None:
        if self._is_cancelled:
            raise _RenameCancelled()

    @staticmethod
    def _unique_temp_path(source: Path) -> Path:
        while True:
            candidate = source.with_name(
                f".musicorg-rename-{uuid4().hex}{source.suffix}"
            )
            if not candidate.exists():
                return candidate

    @staticmethod
    def _build_summary(
        *,
        renamed: int,
        total: int,
        metadata_updated: int,
        metadata_failed: list[FileRenameFailure],
    ) -> FileRenameSummary:
        return {
            "renamed": renamed,
            "total": total,
            "metadata_updated": metadata_updated,
            "metadata_failed": metadata_failed,
        }
