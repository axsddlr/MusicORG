"""Theme framework constants."""

from __future__ import annotations

DEFAULT_THEME_ID = "musicorg-default"
THEME_SCHEMA_VERSION = "1"

REQUIRED_TOKEN_KEYS: tuple[str, ...] = (
    "canvas",
    "surface_0",
    "surface_1",
    "surface_2",
    "surface_3",
    "line_soft",
    "line_strong",
    "text_primary",
    "text_muted",
    "text_dim",
    "accent",
    "accent_hover",
    "accent_press",
    "accent_subtle",
    "danger",
    "success",
    "focus_ring",
)

FONT_KEYS: tuple[str, ...] = (
    "body",
    "display",
    "icon",
)
