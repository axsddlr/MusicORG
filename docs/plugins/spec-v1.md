# Plugin Manifest Spec v1

Required files:

```text
my-plugin/
  manifest.json
  plugin.py (or package module used by entrypoint)
```

Manifest keys:
- `schema_version` (string, required, must be `"1"`)
- `plugin_id` (string, required, lowercase `a-z0-9-`)
- `name` (string, required)
- `version` (string, semver-like, required)
- `author` (string, required)
- `description` (string, required)
- `target_app_min` (string, semver-like, required)
- `entrypoint` (string, required, `module:Class`)
- `capabilities` (string array, required)
- `ui` (object, optional metadata)

Example:

```json
{
  "schema_version": "1",
  "plugin_id": "hello-sidebar",
  "name": "Hello Sidebar",
  "version": "0.1.0",
  "author": "you",
  "description": "Adds a sidebar page.",
  "target_app_min": "0.5.0",
  "entrypoint": "plugin:Plugin",
  "capabilities": ["ui.sidebar_page", "library.read"]
}
```

Supported capabilities:
- `ui.sidebar_page`
- `ui.tool_action`
- `ui.status_strip_card`
- `library.read`
- `library.write_tags`
- `audio.output`
- `worker.background`
- `network.http`
