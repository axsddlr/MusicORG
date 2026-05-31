"""Worker for Quick Tag application."""

from __future__ import annotations

from pathlib import Path

from musicorg.core.tagger import TagData, TagManager
from musicorg.workers.base_worker import BaseWorker


class QuickTagWorker(BaseWorker):
    """Applies quick-tag presets to files in a background thread."""

    def __init__(
        self,
        paths: list[str | Path],
        tags_to_apply: list[str],
        target_field: str = "comment",
        *,
        append_mode: bool = True,
    ) -> None:
        super().__init__()
        self._paths = [str(p) for p in paths]
        self._tags = tags_to_apply
        self._target_field = target_field
        self._append_mode = append_mode

    def run(self) -> None:
        self.started.emit()
        tm = TagManager()
        total = len(self._paths)
        applied = 0
        errors: list[str] = []
        for i, path_str in enumerate(self._paths):
            if self._is_cancelled:
                self.cancelled.emit()
                return
            path = Path(path_str)
            self.progress.emit(i, total, f"Quick Tag: {path.name}")
            try:
                current_tags = tm.read(path)

                new_value = "; ".join(self._tags)
                if self._append_mode and self._target_field == "comment":
                    existing = (current_tags.comment or "").strip()
                    if existing:
                        for tag_val in self._tags:
                            if tag_val.lower() not in existing.lower():
                                existing = f"{existing}; {tag_val}"
                        new_value = existing
                    else:
                        new_value = "; ".join(self._tags)
                elif self._append_mode and self._target_field == "genre":
                    existing = (current_tags.genre or "").strip()
                    if existing:
                        new_parts = existing.split(", ")
                        for tag_val in self._tags:
                            if tag_val not in new_parts:
                                new_parts.append(tag_val)
                        new_value = ", ".join(new_parts)
                    else:
                        new_value = ", ".join(self._tags)

                tag_data = self._build_tag_data(current_tags, self._target_field, new_value)
                tm.write(path, tag_data)
                applied += 1
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
        self.progress.emit(total, total, f"Applied tags to {applied}/{total} files")
        self.finished.emit({"applied": applied, "total": total, "errors": errors})

    def _build_tag_data(
        self, current: TagData, target_field: str, new_value: str
    ) -> TagData:
        kwargs: dict = {
            "title": current.title,
            "artist": current.artist,
            "album": current.album,
            "albumartist": current.albumartist,
            "track": current.track,
            "disc": current.disc,
            "year": current.year,
            "genre": current.genre,
            "composer": current.composer,
            "comment": current.comment,
            "lyrics": current.lyrics,
        }
        if target_field in kwargs:
            kwargs[target_field] = new_value
        return TagData(**kwargs)
