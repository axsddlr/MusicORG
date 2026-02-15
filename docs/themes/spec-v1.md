# MusicOrg Theme Specification v1

## Schema Version
- Current schema: `1`
- `manifest.json` must include `"schema_version": "1"`

## Plug-And-Play Rules
- Theme must be a folder inside the active user themes directory.
  - default directory: `%APPDATA%/musicorg/themes`
  - can be changed in `Settings > Themes...`
- File names must match exactly:
  - `manifest.json`
  - `tokens.json`
  - `fonts.json` (optional)
  - `overrides.qss` (optional)
- The folder name can be anything, but matching folder name to `theme_id` is recommended.
- `theme_id` must be globally unique in your installation.

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

Any missing key rejects the theme during load.

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

If `fonts.json` is missing, MusicOrg default fonts are used.

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
- Unknown keys in `manifest.json`, `tokens.json`, or `fonts.json`: reject theme.
- Multi-line values in manifest fields: reject theme.
- Duplicate `theme_id`: user theme wins over built-in only if valid.

## Color Value Format
`tokens.json` color values currently support:
- Hex colors: `#RGB`, `#RRGGBB`, `#RRGGBBAA`
- Function forms: `rgb(...)`, `rgba(...)`, `hsl(...)`, `hsla(...)`

Example valid values:
- `"#1db954"`
- `"rgba(29,185,84,0.9)"`
- `"hsl(141, 73%, 42%)"`

## Security Constraints
- No executable files are loaded.
- No remote URL includes for styles.
- No dynamic code evaluation from theme packages.
- `overrides.qss` cannot contain `@import` or `url(...)`.
- Symlink theme directories are skipped.

## Size and Input Limits
MusicOrg applies conservative parsing limits to reduce abuse risk:
- `manifest.json` max size: 32 KB
- `tokens.json` max size: 64 KB
- `fonts.json` max size: 32 KB
- `overrides.qss` max size: 128 KB
- preview image max size: 8 MB

Additional limits:
- `theme_id` max length: 64 chars
- manifest short fields max length: 120 chars
- `description` max length: 240 chars
- font string max length: 256 chars
