# Plugins Overview

MusicOrg supports local plugins loaded from plugin package folders.

High-level flow:
1. Runtime discovers plugin folders in built-in and user plugin roots.
2. Each `manifest.json` is validated against schema v1.
3. Enabled plugins are imported and lifecycle hooks are called.
4. Plugins can contribute sidebar pages and tool actions.
5. Plugin errors are isolated and shown in `Settings > Plugins...`.

Default user plugin folder:
- Windows: `%APPDATA%/musicorg/plugins`

Safe mode:
- `Settings > Plugins...` includes safe mode.
- Safe mode keeps built-in plugins only and skips third-party startup.

Plugin-local dependencies:
- Runtime auto-loads `<plugin>/site-packages` into `sys.path`.
- Runtime checks `<plugin>/bin` for native libraries (including optional `libmpv` hints).
