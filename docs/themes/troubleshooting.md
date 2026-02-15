# Theme Troubleshooting

## Theme Does Not Appear in Theme List
Check:
- Folder is inside `%APPDATA%/musicorg/themes`
- `manifest.json` exists and includes required fields
- `tokens.json` exists and includes all required token keys
- JSON syntax is valid (no trailing commas, proper quotes)

## Theme Appears But Cannot Be Applied
Likely causes:
- One or more token color values are invalid
- Unsupported schema version in `manifest.json`
- Invalid values in `fonts.json`

Expected behavior:
- MusicOrg rejects invalid theme and keeps the previous valid theme.

## UI Looks Broken or Hard to Read
Common issues:
- Low contrast between `text_primary` and surface tokens
- Accent colors too close to surface colors
- Aggressive `overrides.qss` selectors

Fix:
1. Revert overrides first.
2. Restore baseline token values.
3. Adjust one token group at a time and retest.

## App Starts With Default Theme Instead of Custom Theme
Possible reasons:
- Selected theme was deleted or renamed
- Theme failed validation after update
- Corrupt theme file

Expected behavior:
- App falls back to default theme or last known good theme.

## How to Reset Quickly
1. Move problematic theme folder out of user themes path.
2. Reopen app.
3. Select default theme in settings.
4. Reintroduce fixed theme files and reload.

## Before Reporting a Bug
Collect:
- Theme folder structure
- `manifest.json` and `tokens.json` contents
- Exact apply error message
- App version and OS version
