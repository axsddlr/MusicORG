"""Theme package discovery and registry."""

from __future__ import annotations

from pathlib import Path

from musicorg.ui.themes.loader import load_theme_package
from musicorg.ui.themes.models import ThemePackage, ThemeSummary, ThemeValidationError

_MAX_THEME_DIR_CANDIDATES = 512


class ThemeRegistry:
    """Loads theme packages from builtin and user directories."""

    def __init__(self, builtin_root: Path, user_root: Path) -> None:
        self._builtin_root = builtin_root
        self._user_root = user_root
        self._themes: dict[str, ThemePackage] = {}
        self._load_errors: list[str] = []

    @property
    def builtin_root(self) -> Path:
        return self._builtin_root

    @property
    def user_root(self) -> Path:
        return self._user_root

    def set_user_root(self, path: Path) -> None:
        self._user_root = path

    def reload(self) -> None:
        self._themes = {}
        self._load_errors = []
        self._load_from_root(self._builtin_root, is_builtin=True, can_override=False)
        self._load_from_root(self._user_root, is_builtin=False, can_override=True)

    def list_themes(self) -> list[ThemeSummary]:
        rows = [
            ThemeSummary(
                theme_id=package.manifest.theme_id,
                name=package.manifest.name,
                version=package.manifest.version,
                author=package.manifest.author,
                description=package.manifest.description,
                is_builtin=package.is_builtin,
                source_dir=package.source_dir,
                preview_path=package.preview_path,
            )
            for package in self._themes.values()
        ]
        return sorted(rows, key=lambda row: (0 if row.is_builtin else 1, row.name.lower()))

    def get_theme(self, theme_id: str) -> ThemePackage | None:
        return self._themes.get(theme_id)

    def load_errors(self) -> list[str]:
        return list(self._load_errors)

    def _load_from_root(self, root: Path, *, is_builtin: bool, can_override: bool) -> None:
        if not root.exists():
            return
        try:
            all_dirs = sorted(path for path in root.iterdir() if path.is_dir())
        except OSError as exc:
            self._load_errors.append(f"Failed to list themes in {root}: {exc}")
            return

        candidates: list[Path] = []
        for path in all_dirs:
            if path.is_symlink():
                self._load_errors.append(f"Skipping symlink theme directory: {path}")
                continue
            candidates.append(path)
        if len(candidates) > _MAX_THEME_DIR_CANDIDATES:
            self._load_errors.append(
                f"Theme directory limit exceeded in {root}; "
                f"only first {_MAX_THEME_DIR_CANDIDATES} folders were scanned."
            )
            candidates = candidates[:_MAX_THEME_DIR_CANDIDATES]

        for theme_dir in candidates:
            try:
                package = load_theme_package(theme_dir, is_builtin=is_builtin)
            except ThemeValidationError as exc:
                self._load_errors.append(str(exc))
                continue

            theme_id = package.manifest.theme_id
            existing = self._themes.get(theme_id)
            if existing is not None and not can_override:
                self._load_errors.append(
                    f"Duplicate builtin theme id {theme_id!r} at {theme_dir}; skipping."
                )
                continue
            if existing is not None and can_override:
                self._load_errors.append(
                    f"User theme {theme_id!r} overrides built-in theme."
                )
            self._themes[theme_id] = package
