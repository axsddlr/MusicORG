"""Theme framework models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ThemeValidationError(ValueError):
    """Raised when a theme package fails validation."""


@dataclass(frozen=True, slots=True)
class ThemeManifest:
    """Theme metadata parsed from manifest.json."""

    schema_version: str
    theme_id: str
    name: str
    version: str
    author: str
    description: str
    target_app_min: str


@dataclass(frozen=True, slots=True)
class ThemePackage:
    """A fully loaded theme package."""

    manifest: ThemeManifest
    tokens: dict[str, str]
    fonts: dict[str, str]
    overrides_qss: str
    source_dir: Path
    is_builtin: bool
    preview_path: Path | None = None


@dataclass(frozen=True, slots=True)
class ThemeSummary:
    """Display-ready theme metadata."""

    theme_id: str
    name: str
    version: str
    author: str
    description: str
    is_builtin: bool
    source_dir: Path
    preview_path: Path | None = None
