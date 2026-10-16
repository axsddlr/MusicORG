# Plugin API Reference

Entrypoint lifecycle (`module:Class`):

```python
class Plugin:
    def initialize(self, context): ...
    def start(self): ...
    def stop(self): ...
    def dispose(self): ...
```

Optional hooks:

```python
def register_sidebar_pages(self) -> list[SidebarPageSpec]: ...
def register_tools_actions(self) -> list[ToolActionSpec]: ...
def on_event(self, event: PluginEvent) -> None: ...
```

`PluginContext` methods:
- `has_capability(capability) -> bool`
- `require_capability(capability) -> None`
- `selected_paths() -> list[pathlib.Path]` (`library.read` required)
- `show_status(message, timeout_ms=2500) -> None`
- `get_setting(key, default=None) -> object`
- `set_setting(key, value) -> None`

Event names:
- `selection.changed` payload: `{"total": int, "selected": int}`
- `scan.completed` payload: `{"count": int}`
- `theme.changed` payload: `{"theme_id": str}`
- `app.shutting_down` payload: `{}`
