"""Theme compilation helpers."""

from __future__ import annotations

from musicorg.ui.theme import build_stylesheet
from musicorg.ui.themes.models import ThemePackage


def compile_theme_stylesheet(theme: ThemePackage) -> str:
    """Compile a theme package into an application stylesheet."""
    return build_stylesheet(
        tokens=theme.tokens,
        fonts=theme.fonts,
        extra_stylesheet=theme.overrides_qss,
    )
