"""Theme package parsing and validation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping

from musicorg.ui.themes.constants import FONT_KEYS, REQUIRED_TOKEN_KEYS, THEME_SCHEMA_VERSION
from musicorg.ui.themes.models import ThemeManifest, ThemePackage, ThemeValidationError

_THEME_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_FUNC_COLOR_RE = re.compile(r"^(?:rgb|rgba|hsl|hsla)\([^)]+\)$", re.IGNORECASE)


def load_theme_package(theme_dir: Path, *, is_builtin: bool = False) -> ThemePackage:
    """Load and validate a single theme package directory."""
    if not theme_dir.exists() or not theme_dir.is_dir():
        raise ThemeValidationError(f"Theme path is not a directory: {theme_dir}")

    manifest_data = _load_json(theme_dir / "manifest.json")
    manifest = _parse_manifest(manifest_data, theme_dir)
    tokens_data = _load_json(theme_dir / "tokens.json")
    tokens = _parse_tokens(tokens_data, theme_dir)

    fonts: dict[str, str] = {}
    fonts_path = theme_dir / "fonts.json"
    if fonts_path.exists():
        fonts = _parse_fonts(_load_json(fonts_path), theme_dir)

    overrides_qss = ""
    overrides_path = theme_dir / "overrides.qss"
    if overrides_path.exists():
        try:
            overrides_qss = overrides_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ThemeValidationError(
                f"Failed to read overrides.qss in {theme_dir}: {exc}"
            ) from exc

    preview_path = _find_preview_path(theme_dir)

    return ThemePackage(
        manifest=manifest,
        tokens=tokens,
        fonts=fonts,
        overrides_qss=overrides_qss,
        source_dir=theme_dir,
        is_builtin=is_builtin,
        preview_path=preview_path,
    )


def _load_json(path: Path) -> Mapping[str, object]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ThemeValidationError(f"Unable to read {path}: {exc}") from exc
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ThemeValidationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ThemeValidationError(f"Expected JSON object in {path}")
    return data


def _parse_manifest(data: Mapping[str, object], theme_dir: Path) -> ThemeManifest:
    schema_version = _required_str(data, "schema_version", theme_dir)
    if schema_version != THEME_SCHEMA_VERSION:
        raise ThemeValidationError(
            f"{theme_dir}: unsupported schema_version {schema_version!r}; "
            f"expected {THEME_SCHEMA_VERSION!r}"
        )

    theme_id = _required_str(data, "theme_id", theme_dir)
    if not _THEME_ID_RE.match(theme_id):
        raise ThemeValidationError(
            f"{theme_dir}: theme_id must match pattern [a-z0-9-], got {theme_id!r}"
        )

    return ThemeManifest(
        schema_version=schema_version,
        theme_id=theme_id,
        name=_required_str(data, "name", theme_dir),
        version=_required_str(data, "version", theme_dir),
        author=_required_str(data, "author", theme_dir),
        description=_required_str(data, "description", theme_dir),
        target_app_min=_required_str(data, "target_app_min", theme_dir),
    )


def _parse_tokens(data: Mapping[str, object], theme_dir: Path) -> dict[str, str]:
    missing = [key for key in REQUIRED_TOKEN_KEYS if key not in data]
    if missing:
        joined = ", ".join(sorted(missing))
        raise ThemeValidationError(f"{theme_dir}: missing required token keys: {joined}")

    tokens: dict[str, str] = {}
    for key in REQUIRED_TOKEN_KEYS:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ThemeValidationError(f"{theme_dir}: token {key!r} must be a non-empty string")
        cleaned = value.strip()
        if not _is_valid_color(cleaned):
            raise ThemeValidationError(f"{theme_dir}: token {key!r} has invalid color {cleaned!r}")
        tokens[key] = cleaned
    return tokens


def _parse_fonts(data: Mapping[str, object], theme_dir: Path) -> dict[str, str]:
    fonts: dict[str, str] = {}
    for key in FONT_KEYS:
        raw = data.get(key)
        if raw is None:
            continue
        if not isinstance(raw, str) or not raw.strip():
            raise ThemeValidationError(f"{theme_dir}: font {key!r} must be a non-empty string")
        fonts[key] = raw.strip()
    return fonts


def _required_str(data: Mapping[str, object], key: str, theme_dir: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ThemeValidationError(f"{theme_dir}: field {key!r} must be a non-empty string")
    return value.strip()


def _is_valid_color(value: str) -> bool:
    if _HEX_COLOR_RE.match(value):
        return True
    if _FUNC_COLOR_RE.match(value):
        return True
    return False


def _find_preview_path(theme_dir: Path) -> Path | None:
    candidates = (
        theme_dir / "preview.png",
        theme_dir / "preview.jpg",
        theme_dir / "preview.jpeg",
        theme_dir / "preview.webp",
    )
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None
