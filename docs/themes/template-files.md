# Theme Template Files (Copy/Paste)

Use this when you want the fastest "drop folder and run" setup.

## Folder Structure
```text
my-theme/
  manifest.json
  tokens.json
  fonts.json            # optional
```

## `manifest.json`
```json
{
  "schema_version": "1",
  "theme_id": "my-theme",
  "name": "My Theme",
  "version": "0.1.0",
  "author": "Your Name",
  "description": "Short theme description",
  "target_app_min": "0.5.0"
}
```

## `tokens.json`
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

## Optional `fonts.json`
```json
{
  "body": "\"Noto Sans\", \"Segoe UI\", sans-serif",
  "display": "\"Bahnschrift\", \"Segoe UI\", sans-serif",
  "icon": "\"Segoe Fluent Icons\", \"Segoe MDL2 Assets\", sans-serif"
}
```

## Apply Steps
1. Place folder in `%APPDATA%/musicorg/themes`.
2. Open `Settings > Themes...`.
3. Click `Reload Themes`.
4. Select your theme and click `OK`.
