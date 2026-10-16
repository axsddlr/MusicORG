"""Tests for plugin framework loader, registry, and runtime basics."""

from __future__ import annotations

import json
from pathlib import Path

from musicorg.plugins.loader import PluginLoader, PluginSearchRoot
from musicorg.plugins.runtime import PluginRuntime


class FakeSettings:
    def __init__(self, plugins_dir: Path) -> None:
        self.plugins_dir_path = plugins_dir
        self.plugins_safe_mode = False
        self.plugin_enabled_map: dict[str, bool] = {}
        self.plugin_crash_counters: dict[str, int] = {}
        self.plugin_startup_timeout_ms = 4000
        self._plugin_data: dict[str, object] = {}

    def plugin_get_setting(self, plugin_id: str, key: str, default: object | None = None) -> object:
        return self._plugin_data.get(f"{plugin_id}:{key}", default)

    def plugin_set_setting(self, plugin_id: str, key: str, value: object) -> None:
        self._plugin_data[f"{plugin_id}:{key}"] = value


class FakeHost:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def get_selected_paths(self) -> list[Path]:
        return []

    def show_status_message(self, message: str, timeout_ms: int = 2500) -> None:
        _ = timeout_ms
        self.messages.append(message)


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_plugin(plugin_dir: Path, manifest: dict[str, object], plugin_source: str) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    _write_json(plugin_dir / "manifest.json", manifest)
    (plugin_dir / "plugin.py").write_text(plugin_source, encoding="utf-8")


def test_loader_discovers_valid_plugin(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    plugin_dir = root / "example"
    _write_plugin(
        plugin_dir,
        {
            "schema_version": "1",
            "plugin_id": "example-plugin",
            "name": "Example",
            "version": "0.1.0",
            "author": "tests",
            "description": "example plugin",
            "target_app_min": "0.5.0",
            "entrypoint": "plugin:Plugin",
            "capabilities": ["ui.sidebar_page"],
        },
        "class Plugin:\n"
        "    def initialize(self, context):\n"
        "        self.context = context\n"
        "    def start(self):\n"
        "        return\n"
        "    def stop(self):\n"
        "        return\n"
        "    def dispose(self):\n"
        "        return\n",
    )

    loader = PluginLoader([PluginSearchRoot(path=root, is_builtin=False)])
    descriptors, errors = loader.discover()

    assert len(descriptors) == 1
    assert not errors
    assert descriptors[0].manifest.plugin_id == "example-plugin"


def test_loader_rejects_unknown_manifest_key(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    plugin_dir = root / "broken"
    _write_plugin(
        plugin_dir,
        {
            "schema_version": "1",
            "plugin_id": "broken-plugin",
            "name": "Broken",
            "version": "0.1.0",
            "author": "tests",
            "description": "broken plugin",
            "target_app_min": "0.5.0",
            "entrypoint": "plugin:Plugin",
            "capabilities": ["ui.sidebar_page"],
            "evil": "nope",
        },
        "class Plugin:\n"
        "    def initialize(self, context):\n"
        "        self.context = context\n"
        "    def start(self):\n"
        "        return\n"
        "    def stop(self):\n"
        "        return\n"
        "    def dispose(self):\n"
        "        return\n",
    )

    loader = PluginLoader([PluginSearchRoot(path=root, is_builtin=False)])
    descriptors, errors = loader.discover()

    assert descriptors == []
    assert any("unsupported keys" in message for message in errors)


def test_runtime_blocks_sidebar_hook_without_capability(tmp_path: Path) -> None:
    user_root = tmp_path / "user-plugins"
    plugin_dir = user_root / "bad-sidebar"
    _write_plugin(
        plugin_dir,
        {
            "schema_version": "1",
            "plugin_id": "bad-sidebar",
            "name": "Bad Sidebar",
            "version": "0.1.0",
            "author": "tests",
            "description": "tries to register page without capability",
            "target_app_min": "0.5.0",
            "entrypoint": "plugin:Plugin",
            "capabilities": ["library.read"],
        },
        "from musicorg.plugins.hooks import SidebarPageSpec\n"
        "class Plugin:\n"
        "    def initialize(self, context):\n"
        "        self.context = context\n"
        "    def start(self):\n"
        "        return\n"
        "    def stop(self):\n"
        "        return\n"
        "    def dispose(self):\n"
        "        return\n"
        "    def register_sidebar_pages(self):\n"
        "        return [SidebarPageSpec(page_id='x', title='X', widget_factory=lambda parent: None)]\n",
    )

    settings = FakeSettings(user_root)
    host = FakeHost()
    runtime = PluginRuntime(settings, builtin_root=tmp_path / "builtin")
    runtime.start(host)

    summaries = {entry.plugin_id: entry for entry in runtime.available_plugins()}
    assert "bad-sidebar" in summaries
    assert summaries["bad-sidebar"].state.value == "failed"
    assert any("ui.sidebar_page" in message for message in runtime.load_errors())


def test_runtime_blocks_bottom_bar_hook_without_capability(tmp_path: Path) -> None:
    user_root = tmp_path / "user-plugins"
    plugin_dir = user_root / "bad-bottom"
    _write_plugin(
        plugin_dir,
        {
            "schema_version": "1",
            "plugin_id": "bad-bottom",
            "name": "Bad Bottom",
            "version": "0.1.0",
            "author": "tests",
            "description": "tries to register bottom bar without capability",
            "target_app_min": "0.5.0",
            "entrypoint": "plugin:Plugin",
            "capabilities": ["library.read"],
        },
        "from PySide6.QtWidgets import QLabel\n"
        "from musicorg.plugins.hooks import BottomBarSpec\n"
        "class Plugin:\n"
        "    def initialize(self, context):\n"
        "        self.context = context\n"
        "    def start(self):\n"
        "        return\n"
        "    def stop(self):\n"
        "        return\n"
        "    def dispose(self):\n"
        "        return\n"
        "    def register_bottom_bars(self):\n"
        "        return [BottomBarSpec(bar_id='x', widget_factory=lambda parent: QLabel('x', parent))]\n",
    )

    settings = FakeSettings(user_root)
    host = FakeHost()
    runtime = PluginRuntime(settings, builtin_root=tmp_path / "builtin")
    runtime.start(host)

    summaries = {entry.plugin_id: entry for entry in runtime.available_plugins()}
    assert "bad-bottom" in summaries
    assert summaries["bad-bottom"].state.value == "failed"
    assert any("ui.status_strip_card" in message for message in runtime.load_errors())


def test_loader_activates_plugin_site_packages(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    plugin_dir = root / "vendor-test"
    _write_plugin(
        plugin_dir,
        {
            "schema_version": "1",
            "plugin_id": "vendor-test",
            "name": "Vendor Test",
            "version": "0.1.0",
            "author": "tests",
            "description": "loads helper from plugin local site-packages",
            "target_app_min": "0.5.0",
            "entrypoint": "plugin:Plugin",
            "capabilities": [],
        },
        "from helper_mod import HELLO\n"
        "class Plugin:\n"
        "    def initialize(self, context):\n"
        "        self.context = context\n"
        "        self.message = HELLO\n"
        "    def start(self):\n"
        "        return\n"
        "    def stop(self):\n"
        "        return\n"
        "    def dispose(self):\n"
        "        return\n",
    )
    site_packages = plugin_dir / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    (site_packages / "helper_mod.py").write_text("HELLO = 'ok'\n", encoding="utf-8")

    loader = PluginLoader([PluginSearchRoot(path=root, is_builtin=False)])
    descriptors, errors = loader.discover()
    assert not errors
    assert len(descriptors) == 1
    instance = loader.load_entrypoint(descriptors[0])
    assert instance is not None
