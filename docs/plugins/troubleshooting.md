# Plugin Troubleshooting

Plugin not listed:
- verify folder contains `manifest.json`
- verify `plugin_id` format (`a-z0-9-`)
- verify `entrypoint` module file exists

Plugin listed but not running:
- open `Settings > Plugins...` and check Diagnostics panel
- check capability declarations for hooks you use
- verify `target_app_min` is not newer than app version

Plugin auto-disabled:
- plugin exceeded crash threshold
- re-enable in `Settings > Plugins...` after fixing errors

Safe mode confusion:
- safe mode keeps built-in plugins only
- disable safe mode and reload if testing third-party plugins
