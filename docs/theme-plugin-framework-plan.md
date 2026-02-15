# MusicOrg Theme Plugin Framework Plan

## Objective
Enable user-created themes that can be installed, validated, selected, and applied across the entire MusicOrg UI with safe fallback behavior and complete end-user documentation.

## Why This Is Needed
- Current theming is static and embedded in `musicorg/ui/theme.py`.
- Styles are applied once at app startup from `musicorg/app.py`.
- Users cannot create or switch themes without changing source code.

## Desired Outcomes
- Users can build themes without touching app code.
- Themes can be applied globally at runtime and persisted.
- Invalid themes never crash the app.
- Theme authors get clear docs, templates, and troubleshooting guidance.

## Non-Goals
- No execution of Python code from theme packages.
- No online theme marketplace in this phase.
- No user-facing visual editor in this phase.

## Current State Summary
- Token and font definitions are currently constants in `musicorg/ui/theme.py`.
- Generated QSS is monolithic and has no plugin loader.
- Settings store UI preferences already, so theme persistence can follow existing patterns in `AppSettings`.

## Architecture Plan

### 1. Theme Domain Model
Create typed models under `musicorg/ui/themes/models.py`.
- `ThemeManifest`
- `ThemePackage`
- `ThemeSummary`
- `ThemeValidationError`

Core fields:
- `theme_id`, `name`, `version`, `author`, `description`
- `schema_version`
- `target_app_min` or compatible app range
- token map and optional font map
- optional preview path and overrides path

### 2. Theme Sources
Support two sources:
- Built-in themes: `musicorg/ui/themes/builtin/`
- User themes: `<app data>/themes/` (Windows: `%APPDATA%/musicorg/themes`)

Precedence:
- If ids collide, valid user theme overrides built-in theme.

### 3. Theme Registry and Loader
Create `musicorg/ui/themes/registry.py`.

Responsibilities:
- Scan both theme roots
- Parse manifests and assets
- Validate and index themes
- Surface load errors as friendly diagnostics

API sketch:
- `reload() -> None`
- `list_themes() -> list[ThemeSummary]`
- `get_theme(theme_id: str) -> ThemePackage | None`
- `load_errors() -> list[str]`

### 4. Compiler and Template Rendering
Refactor theme assembly into dedicated modules:
- `musicorg/ui/themes/defaults.py` for fallback tokens/fonts
- `musicorg/ui/themes/template.py` for stylesheet sections
- `musicorg/ui/themes/compiler.py` for merge + render pipeline

Compile flow:
1. Start with required defaults.
2. Overlay theme tokens.
3. Overlay optional font values.
4. Append optional `overrides.qss`.
5. Produce final stylesheet text.

Validation:
- Required token completeness
- Color value format checks
- Font value sanity checks
- Optional file size guards

### 5. Runtime Theme Service
Create `musicorg/ui/themes/service.py`.

Responsibilities:
- Apply compiled stylesheet to `QApplication`
- Keep last known good theme id
- Revert on errors
- Emit theme-changed signal/event for future hooks

Behavior:
- Apply selected theme immediately in Preferences.
- Persist only after successful apply.
- Revert and notify user if compile/apply fails.

### 6. Settings and UI Integration
Extend `AppSettings` in `musicorg/config/settings.py`:
- `ui/theme_id`
- `ui/theme_last_known_good_id`

Extend `SettingsDialog` in `musicorg/ui/settings_dialog.py`:
- Theme dropdown
- Theme metadata display
- Reload themes button
- Open themes folder button
- Import zip button (phase 2)

Wire startup in `musicorg/app.py`:
- Initialize registry + service
- Resolve and apply configured theme
- Fallback to default if invalid

### 7. Plugin Package Format (Spec v1)
Theme folder layout:

```text
my-theme/
  manifest.json
  tokens.json
  fonts.json            # optional
  overrides.qss         # optional
  preview.png           # optional
  assets/               # optional
```

### 8. Safety Rules
- Never execute code from theme packages.
- Parse JSON only from known files.
- Reject unsupported schema versions.
- Reject missing required tokens.
- Validate color strings before apply.
- Restrict overrides to local stylesheet text only.

## Implementation Phases

### Phase 0: Extraction Baseline
- Extract current theme generation into compiler modules.
- Keep visual parity with existing default theme.
- Add regression test for generated default stylesheet.

### Phase 1: Registry + Validation
- Add scanner for built-in and user paths.
- Parse and validate theme packages.
- Add diagnostics for invalid themes.

### Phase 2: Runtime Apply + Persistence
- Add `ThemeService`.
- Apply selected theme from settings at startup.
- Runtime switching in settings with rollback on failure.

### Phase 3: UX for Theme Management
- Add theme selection controls in settings.
- Add metadata and preview display.
- Add open folder and reload actions.

### Phase 4: Import/Export and Tooling
- Add zip import flow.
- Add theme init template command.
- Add standalone validation command for authors.

### Phase 5: Documentation and Samples
- Publish docs under `docs/themes/`.
- Add one minimal and one advanced sample theme package.

### Phase 6: Hardening and Test Completion
- Unit tests: models, validator, compiler.
- Integration tests: apply, revert, startup fallback.
- Error-path tests: invalid schema, bad colors, missing files.

## Testing Strategy

### Unit Tests
- Manifest parser and validation errors
- Token requirement checks
- Compiler output generation
- Override append behavior

### Integration Tests
- Startup with default theme
- Startup with custom valid theme
- Startup with invalid configured theme (fallback path)
- Runtime switch with settings persistence

### Manual QA
- Create custom theme from docs and apply in app
- Verify all panels/dialogs restyle correctly
- Verify fallback notice and stable UI after invalid theme

## Risks and Mitigations
- Selector instability breaks custom themes
  - Mitigation: maintain stable objectName selector contract and document it.
- Unreadable user themes
  - Mitigation: required token set + contrast guidance in docs.
- Runtime flicker on apply
  - Mitigation: compile once, apply once, avoid iterative partial updates.

## Deliverables
- Theme framework modules under `musicorg/ui/themes/`
- Settings integration for theme selection and management
- Startup/runtime theme application service with fallback
- Theme package spec and author docs in `docs/themes/`
- Tests for validation, compile, apply, and fallback flows

## Acceptance Criteria
- User can add a theme folder and apply it without restarting.
- Theme survives app restart via settings persistence.
- Invalid themes are skipped or rejected with clear error message.
- App always has a valid fallback theme.
- Documentation is sufficient for first-time theme authors.
