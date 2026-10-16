# Plugin Quickstart

1. Create folder in plugins directory, example: `%APPDATA%/musicorg/plugins/hello-sidebar`.
2. Add `manifest.json`.
3. Add entrypoint module/class from `entrypoint`.
4. Open MusicOrg, go to `Settings > Plugins...`, click `Reload Plugins`.
5. Enable your plugin.

Minimal plugin:

```python
from PySide6.QtWidgets import QLabel
from musicorg.plugins.hooks import SidebarPageSpec

class Plugin:
    def initialize(self, context):
        self.context = context
    def start(self): ...
    def stop(self): ...
    def dispose(self): ...
    def register_sidebar_pages(self):
        return [SidebarPageSpec(
            page_id="hello",
            title="Hello",
            icon="H",
            widget_factory=lambda parent: QLabel("Hello from plugin", parent),
        )]
```
