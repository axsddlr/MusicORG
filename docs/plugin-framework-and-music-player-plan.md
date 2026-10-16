# MusicOrg Plugin Framework + Music Player Plugin Plan

## Goal
Build a safe, extensible plugin framework so users can add features to MusicOrg, then deliver the first major plugin: a MusicBee-style music player experience.

## Success Criteria
- Users can install, enable, disable, and remove plugins without editing core app code.
- Plugins can contribute UI, actions, and background tasks through a stable API.
- Plugin loading failures never crash MusicOrg startup.
- Untrusted plugin behavior is constrained by capability/permission checks.
- First player plugin supports real playback workflow end-to-end.

## Scope
- In scope:
  - plugin loader/runtime
  - plugin API contracts
  - plugin settings and lifecycle
  - plugin manager UI
  - plugin author documentation and templates
  - first-party music player plugin
- Out of scope (phase-later):
  - remote plugin marketplace
  - cloud sync of plugin settings
  - DRM/proprietary codec support

## Current Architecture Constraints
- Main UI shell is `musicorg/ui/main_window.py` with:
  - stacked pages: Source, Sync, Duplicates
  - tool dialogs: Tag Editor, Auto-Tag, Artwork Downloader
- Work is threaded via `BaseWorker` + `QThread` patterns in `musicorg/workers`.
- Settings persist through `AppSettings` (`QSettings`).
- No general extension points exist today.

---

## 1. Plugin Framework Architecture

## 1.1 Core Components
- `musicorg/plugins/models.py`
  - `PluginManifest`
  - `PluginState`
  - `PluginCapability`
  - `PluginLoadResult`
- `musicorg/plugins/loader.py`
  - discovers plugin packages
  - validates manifest and entrypoint
  - imports plugin module
- `musicorg/plugins/registry.py`
  - tracks installed plugins, enabled state, load errors
- `musicorg/plugins/runtime.py`
  - lifecycle orchestration: initialize/start/stop/dispose
  - capability gating
- `musicorg/plugins/context.py`
  - safe app context exposed to plugins (narrow API)
- `musicorg/plugins/hooks.py`
  - extension points and typed contracts

## 1.2 Plugin Package Format
Each plugin is a folder:

```text
my-plugin/
  manifest.json
  plugin.py
  README.md
  icon.png            # optional
  assets/             # optional
```

Manifest v1:
- `schema_version`
- `plugin_id`
- `name`
- `version`
- `author`
- `description`
- `target_app_min`
- `entrypoint` (example: `plugin:Plugin`)
- `capabilities` (array of approved capabilities)
- `ui` contribution summary (optional metadata)

## 1.3 Plugin Class Contract
Entrypoint class implements:
- `initialize(context) -> None`
- `start() -> None`
- `stop() -> None`
- `dispose() -> None`

Optional hook methods:
- `register_sidebar_pages() -> list[SidebarPageSpec]`
- `register_tools_actions() -> list[ToolActionSpec]`
- `register_shortcuts() -> list[ShortcutSpec]`
- `on_event(event) -> None`

---

## 2. Security and Safety Model

## 2.1 Design Principle
Treat plugin directories as untrusted code/content. Fail closed by default.

## 2.2 Capability Gating
Capabilities required in manifest and enforced by runtime:
- `ui.sidebar_page`
- `ui.tool_action`
- `library.read`
- `library.write_tags`
- `audio.output`
- `worker.background`
- `network.http`

If capability is not declared, API call is blocked.

## 2.3 Isolation Strategy
- Phase 1 (MVP): in-process plugins with strict API boundaries and explicit capability checks.
- Phase 2: optional out-of-process plugin host for untrusted plugins.

## 2.4 Runtime Hardening
- strict manifest schema, key whitelist, value limits
- plugin ID naming constraints
- per-plugin startup timeout
- exception containment with auto-disable-on-crash threshold
- startup with Safe Mode (skip all third-party plugins)
- explicit plugin folder symlink policy

## 2.5 Observability
- plugin log namespace and per-plugin log file
- structured load/start/fail events
- surfaced diagnostics in Plugin Manager UI

---

## 3. Main App Integration Points

## 3.1 UI Contributions
- Sidebar page contributions:
  - plugin can add full page widgets to main stack
- Tools menu contributions:
  - plugin can add tool actions gated by selection context
- Optional status-strip cards:
  - now playing snippet, plugin status indicators

## 3.2 Data/Event Bus
Typed events available to plugins:
- selection changed
- scan completed
- metadata write completed
- theme changed
- app shutting down

## 3.3 Worker Integration
- plugin worker wrapper follows existing `_worker` + `_thread` naming pattern.
- runtime utility for safe worker registration and shutdown cleanup.

---

## 4. Plugin Manager UX

Add `Settings > Plugins...` dialog:
- Installed plugins list
- Enabled toggle
- Version/author/details
- Load errors panel
- Open plugins folder
- Reload plugins
- Safe mode helper text

Persisted settings:
- plugin enabled/disabled map
- plugin directory path (default + optional custom)
- plugin crash counters

---

## 5. Documentation Deliverables

Create docs set:
- `docs/plugins/overview.md`
- `docs/plugins/spec-v1.md`
- `docs/plugins/security.md`
- `docs/plugins/api-reference.md`
- `docs/plugins/quickstart.md`
- `docs/plugins/troubleshooting.md`
- `docs/plugins/template-files.md`
- `docs/plugins/examples/hello-sidebar/`

Documentation requirements:
- exact required files
- complete manifest reference with examples
- capability explanation with risk notes
- lifecycle hook usage and extension examples
- testing and debugging workflow

---

## 6. First Plugin: MusicBee-Style Player

## 6.1 Product Intent
Deliver a modern local-library player workflow:
- browse library
- queue tracks
- playback controls
- now-playing metadata/artwork
- seek/volume/repeat/shuffle

## 6.2 Plugin ID and Capabilities
- `plugin_id`: `pulse-player`
- required capabilities:
  - `ui.sidebar_page`
  - `audio.output`
  - `library.read`
  - `worker.background`

## 6.3 Player MVP Features
- Sidebar page: `Player`
- Queue panel:
  - add selected tracks
  - remove/reorder queue
  - clear queue
- Transport:
  - play/pause
  - next/previous
  - seek bar
  - elapsed/remaining time
  - volume slider + mute
- Playback modes:
  - repeat off/all/one
  - shuffle on/off
- Now Playing:
  - title, artist, album, artwork thumbnail

## 6.4 Technical Implementation Notes
- Use Qt Multimedia stack (`QMediaPlayer` + `QAudioOutput`) inside plugin.
- Keep player engine independent from widget layer:
  - `player_engine.py` for playback state and queue logic
  - `player_page.py` for UI
- Read metadata/artwork from existing tag models where possible.
- Persist plugin-local settings:
  - volume
  - last mode toggles
  - last queue restore option

## 6.5 Nice-to-Have (Phase 2)
- mini-player in status strip
- keyboard media shortcuts
- gapless/crossfade exploration
- play history and smart queue
- waveform/progress preview

---

## 7. Delivery Phases

## Phase A: Framework Foundation
- plugin manifest model + validation
- plugin discovery, load, enable/disable
- startup-safe fallback behavior
- plugin manager dialog (minimal)

## Phase B: Extension Hooks
- sidebar contribution hook
- tool action contribution hook
- event bus and context API
- worker lifecycle helper

## Phase C: Security Hardening
- capability enforcement
- crash containment and auto-disable
- safe mode boot option
- detailed plugin diagnostics

## Phase D: Music Player Plugin MVP
- player engine
- player page
- queue + transport + now playing
- settings persistence

## Phase E: Docs + Templates
- plugin docs set
- starter template plugin
- music player plugin author/developer notes

---

## 8. Testing Strategy

## 8.1 Framework Tests
- manifest validation paths
- duplicate plugin ID conflict handling
- enable/disable persistence
- lifecycle call ordering
- crash containment behavior
- capability-denied behavior

## 8.2 Integration Tests
- plugin contributes sidebar page and action
- plugin reload path
- app startup with broken plugin
- safe mode startup

## 8.3 Player Plugin Tests
- queue operations
- transport state transitions
- repeat/shuffle logic
- seek and timing updates
- teardown/shutdown cleanup

---

## 9. Risks and Mitigations

- Risk: plugin crashes destabilize UI
  - Mitigation: hard exception boundaries + auto-disable + safe mode.
- Risk: unsafe plugin I/O or network abuse
  - Mitigation: capability-gated context API, no direct privileged app objects.
- Risk: API churn breaks plugins
  - Mitigation: versioned plugin API and compatibility checks.
- Risk: playback backend differences by OS
  - Mitigation: backend capability checks + fallback messaging.

---

## 10. Acceptance Criteria

- Plugin framework:
  - can load at least one example plugin with no core code edits
  - survives malformed plugin packages without startup failure
  - users can enable/disable plugins from UI
- Player plugin:
  - can play selected local files reliably
  - queue and transport controls work end-to-end
  - now-playing metadata updates correctly
  - no thread or player resource leaks on shutdown

---

## 11. Immediate Next Step (Execution Order)

1. Implement Phase A skeleton (`plugins/` package + loader/registry/runtime).
2. Add `Settings > Plugins...` manager dialog.
3. Add sidebar contribution hook.
4. Create `pulse-player` plugin with minimal transport + queue.
5. Expand docs under `docs/plugins/` with template files and quickstart.
