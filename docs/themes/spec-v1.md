# MusicOrg Theme Specification v1

## Schema Version
- Current schema: `1`
- `manifest.json` must include `"schema_version": "1"`

## Required Files
- `manifest.json`
- `tokens.json`

## Optional Files
- `fonts.json`
- `overrides.qss`
- `preview.png`
- `assets/`

## Required `manifest.json` Fields
```json
{
  "schema_version": "1",
  "theme_id": "sunset-jazz",
  "name": "Sunset Jazz",
  "version": "0.1.0",
  "author": "Your Name",
  "description": "Warm low-light palette with soft accents",
  "target_app_min": "0.5.0"
}
```

Field rules:
- `theme_id`: lowercase slug, letters/numbers/dashes only
- `name`: display name
- `version`: theme version string
- `author`: author or team name
- `description`: short purpose summary
- `target_app_min`: minimum app version supported by this theme

## Required `tokens.json` Fields
All keys below must be present:
- `canvas`
- `surface_0`
- `surface_1`
- `surface_2`
- `surface_3`
- `line_soft`
- `line_strong`
- `text_primary`
- `text_muted`
- `text_dim`
- `accent`
- `accent_hover`
- `accent_press`
- `accent_subtle`
- `danger`
- `success`
- `focus_ring`

Example:
```json
{
  "canvas": "#0f1117",
  "surface_0": "#151926",
  "surface_1": "#1b2230",
  "surface_2": "#232d3d",
  "surface_3": "#2c3950",
  "line_soft": "#334158",
  "line_strong": "#3f506d",
  "text_primary": "#e7ecf7",
  "text_muted": "#9aa8c4",
  "text_dim": "#76839c",
  "accent": "#d2a64e",
  "accent_hover": "#e1b861",
  "accent_press": "#b98f3c",
  "accent_subtle": "#4f4530",
  "danger": "#d76868",
  "success": "#5fb484",
  "focus_ring": "#8cb6ff"
}
```

## Optional `fonts.json`
```json
{
  "body": "\"Noto Sans\", \"Segoe UI\", sans-serif",
  "display": "\"Bahnschrift\", \"Segoe UI\", sans-serif",
  "icon": "\"Segoe Fluent Icons\", \"Segoe MDL2 Assets\", sans-serif"
}
```

Supported keys:
- `body`
- `display`
- `icon`

## Optional `overrides.qss`
Use this only for advanced selector customization.
- Keep selectors stable and scoped.
- Prefer object names and documented selectors.
- Avoid broad global selectors that can break readability.

## Validation Rules
- Missing required files: reject theme.
- Missing required tokens: reject theme.
- Unknown schema version: reject theme.
- Invalid color format: reject theme.
- Invalid JSON: reject theme.
- Duplicate `theme_id`: user theme wins over built-in only if valid.

## Security Constraints
- No executable files are loaded.
- No remote URL includes for styles.
- No dynamic code evaluation from theme packages.
