# Quickstart: Create Your First MusicOrg Theme

## 1. Locate Theme Folder
Create a new folder inside:
- Windows: `%APPDATA%/musicorg/themes`

Example:
```text
%APPDATA%/musicorg/themes/my-first-theme/
```

## 2. Add Required Files
Create these files in your theme folder:
- `manifest.json`
- `tokens.json`

Optional:
- `fonts.json`
- `overrides.qss`
- `preview.png`

## 3. Add `manifest.json`
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

## 4. Add `tokens.json`
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

## 5. Reload and Apply
In MusicOrg (planned settings flow):
1. Open `Settings > Preferences`
2. Click `Reload Themes`
3. Select your theme in the theme dropdown
4. Apply and verify all panels

## 6. Optional Font Overrides
Add `fonts.json`:
```json
{
  "body": "\"Noto Sans\", \"Segoe UI\", sans-serif",
  "display": "\"Bahnschrift\", \"Segoe UI\", sans-serif",
  "icon": "\"Segoe Fluent Icons\", \"Segoe MDL2 Assets\", sans-serif"
}
```

## 7. Troubleshooting
- Theme not listed: check JSON validity and required fields.
- App falls back to default: one or more values failed validation.
- Text hard to read: increase contrast between surfaces and text tokens.

For more detail, read:
- `docs/themes/spec-v1.md`
- `docs/themes/reference-tokens.md`
- `docs/themes/troubleshooting.md`
