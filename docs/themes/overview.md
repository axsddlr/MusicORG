# MusicOrg Themes Overview

## Plug-And-Play Summary
To use a custom theme:
1. Open `Settings > Themes... > Open Themes Folder`.
2. Drop a theme folder in that directory.
3. Click `Reload Themes`.
4. Select the theme and click `OK`.

Minimum required files are only:
- `manifest.json`
- `tokens.json`

## What Themes Can Change
MusicOrg themes currently support:
- Color tokens used across app UI components
- Font family tokens for body, display, and icon text
- Optional stylesheet overrides for advanced selectors
- Optional preview image shown in future theme picker UI

## What Themes Cannot Do
- Execute Python or shell code
- Modify business logic
- Access network resources
- Patch files outside the theme directory

## Theme Sources
- Built-in themes are shipped with MusicOrg.
- User themes are loaded from:
  - default: `%APPDATA%/musicorg/themes`
  - or a custom directory set in `Settings > Themes...`

## Selection and Apply Flow
1. MusicOrg scans built-in and user themes.
2. Valid themes appear in `Settings > Themes...`.
3. Selecting a theme compiles QSS from defaults + theme tokens.
4. Theme applies to the running app.
5. Selection is saved in settings and restored on next launch.

## Failure and Fallback
- Invalid themes are rejected during validation.
- If a selected theme cannot be applied, MusicOrg reverts to default theme.
- Last known good theme id is preserved for recovery.

## File Layout
Each theme is a directory with standard files:

```text
my-theme/
  manifest.json
  tokens.json
  fonts.json            # optional
  overrides.qss         # optional
  preview.png           # optional
  assets/               # optional
```

For detailed fields, see:
- `docs/themes/spec-v1.md`
- `docs/themes/quickstart.md`
- `docs/themes/reference-tokens.md`
- `docs/themes/template-files.md`
