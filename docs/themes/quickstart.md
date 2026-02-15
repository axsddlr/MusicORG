# Quickstart: Create Your First MusicOrg Theme

## 1. Open Your Themes Folder
In the app:
1. Go to `Settings > Themes...`
2. Click `Open Themes Folder`
3. Optional: set a custom themes folder first if you do not want to use `%APPDATA%/musicorg/themes`

Example:
```text
%APPDATA%/musicorg/themes
```

## 2. Create a Theme Folder
Create a folder in that path, for example:

```text
%APPDATA%/musicorg/themes/my-first-theme/
```

## 3. Add Required Files
Create these files in `my-first-theme/`:
- `manifest.json`
- `tokens.json`

Optional:
- `fonts.json`
- `overrides.qss`
- `preview.png`

## 4. Add `manifest.json`
```json
{
  "schema_version": "1",
  "theme_id": "my-first-theme",
  "name": "My First Theme",
  "version": "0.1.0",
  "author": "Your Name",
  "description": "My custom MusicOrg theme",
  "target_app_min": "0.5.0"
}
```

## 5. Add `tokens.json`
Start from this baseline:
```json
{
  "canvas": "#0e1015",
  "surface_0": "#12151c",
  "surface_1": "#171b24",
  "surface_2": "#1d2230",
  "surface_3": "#252c3d",
  "line_soft": "#2a3143",
  "line_strong": "#36405a",
  "text_primary": "#e6ebf5",
  "text_muted": "#93a0b8",
  "text_dim": "#6f7b92",
  "accent": "#d4a44a",
  "accent_hover": "#e6b962",
  "accent_press": "#ba8b35",
  "accent_subtle": "#4e452f",
  "danger": "#d76868",
  "success": "#5fb484",
  "focus_ring": "#8cb6ff"
}
```

Change colors gradually, then save.

## 6. Reload and Apply
In MusicOrg:
1. Open `Settings > Themes...`
2. Click `Reload Themes`
3. Select `My First Theme`
4. Click `OK`

## 7. Optional Font Overrides
Add `fonts.json`:
```json
{
  "body": "\"Noto Sans\", \"Segoe UI\", sans-serif",
  "display": "\"Bahnschrift\", \"Segoe UI\", sans-serif",
  "icon": "\"Segoe Fluent Icons\", \"Segoe MDL2 Assets\", sans-serif"
}
```

## 8. Plug-And-Play Checklist
- Folder is inside `%APPDATA%/musicorg/themes`
- `manifest.json` and `tokens.json` exist
- `schema_version` is `"1"`
- `theme_id` is lowercase with dashes only
- All required token keys are present

## 9. Troubleshooting
- Theme not listed: check JSON validity and required fields.
- App falls back to default: one or more values failed validation.
- Text hard to read: increase contrast between surfaces and text tokens.

For more detail, read:
- `docs/themes/spec-v1.md`
- `docs/themes/reference-tokens.md`
- `docs/themes/troubleshooting.md`
