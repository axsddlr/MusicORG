# Packaging and Sharing MusicOrg Themes

## Versioning
Use semantic versioning for your theme:
- Patch: small color/font tweaks
- Minor: noticeable visual update
- Major: large redesign or compatibility break

## Naming
- Use a stable `theme_id` slug (do not change once shared widely).
- Use a human-friendly `name` for display.

## Package Checklist
Before sharing:
- `manifest.json` includes accurate version and compatibility
- `tokens.json` includes all required keys
- Optional `fonts.json` values are valid
- Optional `overrides.qss` is minimal and tested
- Optional `preview.png` reflects current appearance

## Zip Package Format
Zip the theme folder itself (not parent folders), for example:

```text
sunset-jazz.zip
  sunset-jazz/
    manifest.json
    tokens.json
    fonts.json
    overrides.qss
    preview.png
```

## Compatibility Notes
- Include `target_app_min` to indicate minimum supported MusicOrg version.
- Document any known UI assumptions if you rely heavily on `overrides.qss`.

## Changelog Recommendation
Keep a simple `CHANGELOG.md` in your theme folder for collaborators:
- version
- date
- visual changes
- compatibility notes

## Support Guidance
When distributing a theme, provide:
- screenshots of key app views
- tested MusicOrg version
- troubleshooting notes for common install mistakes
