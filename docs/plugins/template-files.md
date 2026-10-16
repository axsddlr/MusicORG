# Template Files

## `manifest.json`

```json
{
  "schema_version": "1",
  "plugin_id": "my-plugin",
  "name": "My Plugin",
  "version": "0.1.0",
  "author": "you",
  "description": "Plugin description",
  "target_app_min": "0.5.0",
  "entrypoint": "plugin:Plugin",
  "capabilities": ["ui.sidebar_page"]
}
```

## `plugin.py`

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
            page_id="my-page",
            title="My Page",
            icon="M",
            widget_factory=lambda parent: QLabel("My Page", parent),
        )]
```
