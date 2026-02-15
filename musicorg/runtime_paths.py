"""Runtime path helpers for source and frozen executable modes."""

from __future__ import annotations

from pathlib import Path
import sys


def is_frozen() -> bool:
    """Return True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Return the runtime extraction root for frozen mode, else package parent."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return Path(__file__).resolve().parent.parent


def package_root() -> Path:
    """Return the root path that contains the `musicorg` package resources."""
    if is_frozen():
        root = bundle_root()
        candidate = root / "musicorg"
        if candidate.exists():
            return candidate
        return root
    return Path(__file__).resolve().parent


def asset_path(*parts: str) -> Path:
    """Resolve a UI asset path across source/frozen runtime layouts."""
    return package_root().joinpath("ui", "assets", *parts)


def builtin_themes_root() -> Path:
    """Resolve the built-in theme directory across source/frozen layouts."""
    return package_root() / "ui" / "themes" / "builtin"

