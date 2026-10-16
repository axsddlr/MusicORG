# Pulse Player Plugin

Built-in plugin that adds a `Player` sidebar page and bottom mini-player bar.

Features:
- add selected tracks from Source
- queue management (remove, move up/down, clear)
- playback controls (play/pause, previous/next, seek)
- shuffle and repeat modes
- volume and mute controls
- now-playing metadata + artwork thumbnail

Playback backend:
- prefers `mpv` when `python-mpv` + `libmpv` are available
- falls back to Qt Multimedia backend if `mpv` is unavailable

Optional plugin-local dependencies:
- `site-packages/` for Python wheels (e.g. `python-mpv`)
- `bin/` for native libs (e.g. `libmpv` / `libmpv-2.dll`)

Install `python-mpv` into this plugin folder:

```powershell
cd musicorg/plugins/builtin/pulse-player
python -m pip install -r requirements.txt --target .\site-packages
```

Then place `libmpv` in `bin/` and reload plugins.

Plugin-local settings:
- `volume` (0-100)
- `muted` (bool)
- `repeat_mode` (`off`/`all`/`one`)
- `shuffle_enabled` (bool)
- `restore_queue` (bool)
- `queue_paths` (list[str])
- `queue_index` (int)
