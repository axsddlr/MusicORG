"""Tests for theme plugin loader and registry behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from musicorg.ui.themes.constants import REQUIRED_TOKEN_KEYS
from musicorg.ui.themes.loader import load_theme_package
from musicorg.ui.themes.models import ThemeValidationError
from musicorg.ui.themes.registry import ThemeRegistry


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _base_manifest(theme_id: str) -> dict[str, object]:
    return {
        "schema_version": "1",
        "theme_id": theme_id,
        "name": theme_id,
        "version": "0.1.0",
        "author": "tests",
        "description": "test theme",
        "target_app_min": "0.5.0",
    }


def _base_tokens() -> dict[str, object]:
    return {key: "#112233" for key in REQUIRED_TOKEN_KEYS}


def _write_theme_dir(theme_dir: Path, theme_id: str, accent: str = "#22aa66") -> None:
    manifest = _base_manifest(theme_id)
    tokens = _base_tokens()
    tokens["accent"] = accent
    _write_json(theme_dir / "manifest.json", manifest)
    _write_json(theme_dir / "tokens.json", tokens)


def test_load_theme_package_valid(tmp_path: Path) -> None:
    theme_dir = tmp_path / "test-theme"
    _write_theme_dir(theme_dir, "test-theme")

    package = load_theme_package(theme_dir)
    assert package.manifest.theme_id == "test-theme"
    assert package.tokens["accent"] == "#22aa66"


def test_load_theme_package_missing_tokens_rejected(tmp_path: Path) -> None:
    theme_dir = tmp_path / "broken-theme"
    _write_json(theme_dir / "manifest.json", _base_manifest("broken-theme"))
    tokens = _base_tokens()
    tokens.pop("accent")
    _write_json(theme_dir / "tokens.json", tokens)

    with pytest.raises(ThemeValidationError):
        load_theme_package(theme_dir)


def test_registry_user_theme_overrides_builtin(tmp_path: Path) -> None:
    builtin_root = tmp_path / "builtin"
    user_root = tmp_path / "user"
    _write_theme_dir(builtin_root / "shared-theme", "shared-theme", accent="#00ff00")
    _write_theme_dir(user_root / "shared-theme", "shared-theme", accent="#ff00ff")

    registry = ThemeRegistry(builtin_root=builtin_root, user_root=user_root)
    registry.reload()

    package = registry.get_theme("shared-theme")
    assert package is not None
    assert package.tokens["accent"] == "#ff00ff"
    assert package.is_builtin is False


def test_registry_rejects_invalid_theme_id(tmp_path: Path) -> None:
    builtin_root = tmp_path / "builtin"
    user_root = tmp_path / "user"
    _write_theme_dir(user_root / "bad", "Bad Theme")

    registry = ThemeRegistry(builtin_root=builtin_root, user_root=user_root)
    registry.reload()

    assert registry.get_theme("Bad Theme") is None
    assert any("theme_id must match pattern" in msg for msg in registry.load_errors())


def test_load_theme_rejects_unknown_token_key(tmp_path: Path) -> None:
    theme_dir = tmp_path / "unknown-token"
    _write_json(theme_dir / "manifest.json", _base_manifest("unknown-token"))
    tokens = _base_tokens()
    tokens["evil_key"] = "#000000"
    _write_json(theme_dir / "tokens.json", tokens)

    with pytest.raises(ThemeValidationError):
        load_theme_package(theme_dir)


def test_load_theme_rejects_manifest_unknown_key(tmp_path: Path) -> None:
    theme_dir = tmp_path / "unknown-manifest"
    manifest = _base_manifest("unknown-manifest")
    manifest["sql"] = "DROP TABLE themes"
    _write_json(theme_dir / "manifest.json", manifest)
    _write_json(theme_dir / "tokens.json", _base_tokens())

    with pytest.raises(ThemeValidationError):
        load_theme_package(theme_dir)


def test_load_theme_rejects_overrides_import_or_url(tmp_path: Path) -> None:
    theme_dir = tmp_path / "bad-overrides"
    _write_theme_dir(theme_dir, "bad-overrides")
    (theme_dir / "overrides.qss").write_text(
        "@import \"http://example.com/evil.qss\";\nQLabel { color: #fff; }",
        encoding="utf-8",
    )

    with pytest.raises(ThemeValidationError):
        load_theme_package(theme_dir)


def test_load_theme_rejects_manifest_field_length_and_newlines(tmp_path: Path) -> None:
    theme_dir = tmp_path / "bad-manifest"
    manifest = _base_manifest("bad-manifest")
    manifest["name"] = "A" * 200
    _write_json(theme_dir / "manifest.json", manifest)
    _write_json(theme_dir / "tokens.json", _base_tokens())
    with pytest.raises(ThemeValidationError):
        load_theme_package(theme_dir)

    manifest["name"] = "bad\nname"
    _write_json(theme_dir / "manifest.json", manifest)
    with pytest.raises(ThemeValidationError):
        load_theme_package(theme_dir)
