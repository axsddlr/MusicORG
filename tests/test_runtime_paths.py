from __future__ import annotations

from pathlib import Path

from musicorg import runtime_paths


def test_source_package_root_points_to_repo_package() -> None:
    root = runtime_paths.package_root()
    assert root.name == "musicorg"
    assert (root / "ui").exists()


def test_source_asset_and_theme_paths_resolve() -> None:
    assert runtime_paths.asset_path("musicorg.ico").name == "musicorg.ico"
    assert runtime_paths.builtin_themes_root().name == "builtin"


def test_frozen_prefers_meipass_musicorg_dir(tmp_path: Path, monkeypatch) -> None:
    bundle_root = tmp_path / "bundle"
    package_root = bundle_root / "musicorg"
    package_root.mkdir(parents=True)
    monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime_paths.sys, "_MEIPASS", str(bundle_root), raising=False)

    assert runtime_paths.package_root() == package_root


def test_frozen_falls_back_to_meipass_when_musicorg_missing(tmp_path: Path, monkeypatch) -> None:
    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir(parents=True)
    monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime_paths.sys, "_MEIPASS", str(bundle_root), raising=False)

    assert runtime_paths.package_root() == bundle_root

