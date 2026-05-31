"""Tag profiles for saving/loading autotag and quicktag configurations."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass
class AutoTagProfile:
    name: str = ""
    enabled_sources: list[str] = field(default_factory=lambda: ["MusicBrainz"])
    overwrite_fields: list[str] = field(default_factory=list)
    fill_empty_only: bool = True
    regex_cleanup_pattern: str = ""
    regex_cleanup_replacement: str = ""
    move_successful_to: str = ""
    move_failed_to: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled_sources": self.enabled_sources,
            "overwrite_fields": self.overwrite_fields,
            "fill_empty_only": self.fill_empty_only,
            "regex_cleanup_pattern": self.regex_cleanup_pattern,
            "regex_cleanup_replacement": self.regex_cleanup_replacement,
            "move_successful_to": self.move_successful_to,
            "move_failed_to": self.move_failed_to,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutoTagProfile:
        return cls(
            name=str(data.get("name", "")),
            enabled_sources=list(data.get("enabled_sources", ["MusicBrainz"])),
            overwrite_fields=list(data.get("overwrite_fields", [])),
            fill_empty_only=bool(data.get("fill_empty_only", True)),
            regex_cleanup_pattern=str(data.get("regex_cleanup_pattern", "")),
            regex_cleanup_replacement=str(data.get("regex_cleanup_replacement", "")),
            move_successful_to=str(data.get("move_successful_to", "")),
            move_failed_to=str(data.get("move_failed_to", "")),
        )


@dataclass
class QuickTagProfile:
    name: str = ""
    tag_presets: list[dict[str, str]] = field(default_factory=list)
    target_field: str = "comment"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tag_presets": self.tag_presets,
            "target_field": self.target_field,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuickTagProfile:
        return cls(
            name=str(data.get("name", "")),
            tag_presets=list(data.get("tag_presets", [])),
            target_field=str(data.get("target_field", "comment")),
        )


DEFAULT_QUICKTAG_PRESETS: list[dict[str, str]] = [
    {"label": "High Energy", "category": "Energy"},
    {"label": "Medium Energy", "category": "Energy"},
    {"label": "Low Energy", "category": "Energy"},
    {"label": "Happy", "category": "Mood"},
    {"label": "Dark", "category": "Mood"},
    {"label": "Emotional", "category": "Mood"},
    {"label": "Tech House", "category": "Genre"},
    {"label": "Deep House", "category": "Genre"},
    {"label": "Techno", "category": "Genre"},
    {"label": "Progressive House", "category": "Genre"},
    {"label": "Melodic House", "category": "Genre"},
    {"label": "Drum & Bass", "category": "Genre"},
    {"label": "Trance", "category": "Genre"},
    {"label": "Hip-Hop", "category": "Genre"},
    {"label": "Disco", "category": "Genre"},
    {"label": "Funk", "category": "Genre"},
    {"label": "Afro House", "category": "Genre"},
    {"label": "Minimal", "category": "Genre"},
    {"label": "Vocal", "category": "Characteristic"},
    {"label": "Instrumental", "category": "Characteristic"},
    {"label": "Peak Time", "category": "Characteristic"},
    {"label": "Warm Up", "category": "Characteristic"},
    {"label": "Closing", "category": "Characteristic"},
    {"label": "Classic", "category": "Characteristic"},
]


class ProfileStore:
    def __init__(self, dir_path: str | Path) -> None:
        self._dir = Path(dir_path)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _autotag_file(self) -> Path:
        return self._dir / "autotag_profiles.json"

    def _quicktag_file(self) -> Path:
        return self._dir / "quicktag_profiles.json"

    def load_autotag_profiles(self) -> list[AutoTagProfile]:
        path = self._autotag_file()
        if not path.exists():
            return [AutoTagProfile(name="Default", enabled_sources=["MusicBrainz"])]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [AutoTagProfile.from_dict(p) for p in data]
        except Exception:
            return [AutoTagProfile(name="Default", enabled_sources=["MusicBrainz"])]

    def save_autotag_profiles(self, profiles: list[AutoTagProfile]) -> None:
        self._autotag_file().write_text(
            json.dumps([p.to_dict() for p in profiles], indent=2),
            encoding="utf-8",
        )

    def load_quicktag_profiles(self) -> list[QuickTagProfile]:
        path = self._quicktag_file()
        if not path.exists():
            return [QuickTagProfile(
                name="Default",
                tag_presets=DEFAULT_QUICKTAG_PRESETS,
                target_field="comment",
            )]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [QuickTagProfile.from_dict(p) for p in data]
        except Exception:
            return [QuickTagProfile(
                name="Default",
                tag_presets=DEFAULT_QUICKTAG_PRESETS,
                target_field="comment",
            )]

    def save_quicktag_profiles(self, profiles: list[QuickTagProfile]) -> None:
        self._quicktag_file().write_text(
            json.dumps([p.to_dict() for p in profiles], indent=2),
            encoding="utf-8",
        )
