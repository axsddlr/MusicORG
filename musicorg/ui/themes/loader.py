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
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")
_BLOCKED_OVERRIDES_RE = re.compile(r"(?:@import|url\s*\()", re.IGNORECASE)

_MAX_MANIFEST_BYTES = 32 * 1024
_MAX_TOKENS_BYTES = 64 * 1024
_MAX_FONTS_BYTES = 32 * 1024
_MAX_OVERRIDES_BYTES = 128 * 1024
_MAX_PREVIEW_BYTES = 8 * 1024 * 1024
_MAX_THEME_ID_LEN = 64
_MAX_SHORT_FIELD_LEN = 120
_MAX_DESC_LEN = 240
_MAX_FONT_VALUE_LEN = 256
_MAX_COLOR_VALUE_LEN = 64


def load_theme_package(theme_dir: Path, *, is_builtin: bool = False) -> ThemePackage:
    """Load and validate a single theme package directory."""
    if not theme_dir.exists() or not theme_dir.is_dir():
        raise ThemeValidationError(f"Theme path is not a directory: {theme_dir}")
    if theme_dir.is_symlink():
        raise ThemeValidationError(f"Theme directory cannot be a symlink: {theme_dir}")

    manifest_data = _load_json(theme_dir / "manifest.json", max_bytes=_MAX_MANIFEST_BYTES)
    manifest = _parse_manifest(manifest_data, theme_dir)
    tokens_data = _load_json(theme_dir / "tokens.json", max_bytes=_MAX_TOKENS_BYTES)
    tokens = _parse_tokens(tokens_data, theme_dir)

    fonts: dict[str, str] = {}
    fonts_path = theme_dir / "fonts.json"
    if fonts_path.exists():
        fonts = _parse_fonts(_load_json(fonts_path, max_bytes=_MAX_FONTS_BYTES), theme_dir)

    overrides_qss = ""
    overrides_path = theme_dir / "overrides.qss"
    if overrides_path.exists():
        overrides_qss = _read_text_limited(overrides_path, max_bytes=_MAX_OVERRIDES_BYTES)
        if _BLOCKED_OVERRIDES_RE.search(overrides_qss):
            raise ThemeValidationError(
                f"{theme_dir}: overrides.qss may not contain @import or url(...) directives"
            )

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


def _load_json(path: Path, *, max_bytes: int) -> Mapping[str, object]:
    content = _read_text_limited(path, max_bytes=max_bytes)
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ThemeValidationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ThemeValidationError(f"Expected JSON object in {path}")
    return data


def _parse_manifest(data: Mapping[str, object], theme_dir: Path) -> ThemeManifest:
    _reject_unknown_keys(
        data,
        allowed={
            "schema_version",
            "theme_id",
            "name",
            "version",
            "author",
            "description",
            "target_app_min",
        },
        context=f"{theme_dir}/manifest.json",
    )

    schema_version = _required_str(data, "schema_version", theme_dir, max_len=8)
    if schema_version != THEME_SCHEMA_VERSION:
        raise ThemeValidationError(
            f"{theme_dir}: unsupported schema_version {schema_version!r}; "
            f"expected {THEME_SCHEMA_VERSION!r}"
        )

    theme_id = _required_str(data, "theme_id", theme_dir, max_len=_MAX_THEME_ID_LEN)
    if not _THEME_ID_RE.match(theme_id):
        raise ThemeValidationError(
            f"{theme_dir}: theme_id must match pattern [a-z0-9-], got {theme_id!r}"
        )

    version = _required_str(data, "version", theme_dir, max_len=40)
    target_app_min = _required_str(data, "target_app_min", theme_dir, max_len=40)
    if not _SEMVER_RE.match(version):
        raise ThemeValidationError(f"{theme_dir}: manifest version must be semver-like, got {version!r}")
    if not _SEMVER_RE.match(target_app_min):
        raise ThemeValidationError(
            f"{theme_dir}: target_app_min must be semver-like, got {target_app_min!r}"
        )

    return ThemeManifest(
        schema_version=schema_version,
        theme_id=theme_id,
        name=_required_str(data, "name", theme_dir, max_len=_MAX_SHORT_FIELD_LEN),
        version=version,
        author=_required_str(data, "author", theme_dir, max_len=_MAX_SHORT_FIELD_LEN),
        description=_required_str(data, "description", theme_dir, max_len=_MAX_DESC_LEN),
        target_app_min=target_app_min,
    )


def _parse_tokens(data: Mapping[str, object], theme_dir: Path) -> dict[str, str]:
    _reject_unknown_keys(
        data,
        allowed=set(REQUIRED_TOKEN_KEYS),
        context=f"{theme_dir}/tokens.json",
    )
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
        if len(cleaned) > _MAX_COLOR_VALUE_LEN:
            raise ThemeValidationError(f"{theme_dir}: token {key!r} value is too long")
        if not _is_valid_color(cleaned):
            raise ThemeValidationError(f"{theme_dir}: token {key!r} has invalid color {cleaned!r}")
        tokens[key] = cleaned
    return tokens


def _parse_fonts(data: Mapping[str, object], theme_dir: Path) -> dict[str, str]:
    _reject_unknown_keys(
        data,
        allowed=set(FONT_KEYS),
        context=f"{theme_dir}/fonts.json",
    )
    fonts: dict[str, str] = {}
    for key in FONT_KEYS:
        raw = data.get(key)
        if raw is None:
            continue
        if not isinstance(raw, str) or not raw.strip():
            raise ThemeValidationError(f"{theme_dir}: font {key!r} must be a non-empty string")
        cleaned = raw.strip()
        if len(cleaned) > _MAX_FONT_VALUE_LEN:
            raise ThemeValidationError(f"{theme_dir}: font {key!r} value is too long")
        fonts[key] = cleaned
    return fonts


def _required_str(data: Mapping[str, object], key: str, theme_dir: Path, *, max_len: int) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ThemeValidationError(f"{theme_dir}: field {key!r} must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > max_len:
        raise ThemeValidationError(f"{theme_dir}: field {key!r} exceeds max length {max_len}")
    if any(ch in cleaned for ch in ("\n", "\r", "\t")):
        raise ThemeValidationError(f"{theme_dir}: field {key!r} must be a single line string")
    return cleaned


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
        if candidate.exists() and candidate.is_file() and not candidate.is_symlink():
            try:
                if candidate.stat().st_size > _MAX_PREVIEW_BYTES:
                    continue
            except OSError:
                continue
            return candidate
    return None


def _reject_unknown_keys(
    data: Mapping[str, object],
    *,
    allowed: set[str],
    context: str,
) -> None:
    unknown = sorted(key for key in data.keys() if key not in allowed)
    if unknown:
        joined = ", ".join(unknown)
        raise ThemeValidationError(f"{context}: unsupported keys found: {joined}")


def _read_text_limited(path: Path, *, max_bytes: int) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ThemeValidationError(f"Unable to stat {path}: {exc}") from exc
    if size > max_bytes:
        raise ThemeValidationError(f"{path}: file exceeds max size ({max_bytes} bytes)")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ThemeValidationError(f"Unable to read {path}: {exc}") from exc
