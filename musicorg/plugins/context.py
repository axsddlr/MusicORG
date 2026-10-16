"""Capability-gated context exposed to plugins."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from musicorg.plugins.hooks import PluginEvent
from musicorg.plugins.models import PluginCapability


class PluginHostApi(Protocol):
    """Safe host surface available through PluginContext."""

    def get_selected_paths(self) -> list[Path]:
        """Return selected source paths from the host application."""

    def show_status_message(self, message: str, timeout_ms: int = 2500) -> None:
        """Display a status message in the host UI."""


class PluginSettingsStore(Protocol):
    """Plugin-local settings persistence helpers."""

    def plugin_get_setting(self, plugin_id: str, key: str, default: object | None = None) -> object:
        """Get a plugin-local setting value from persistent storage."""

    def plugin_set_setting(self, plugin_id: str, key: str, value: object) -> None:
        """Persist a plugin-local setting value."""


@dataclass(slots=True)
class PluginContext:
    """Narrow, capability-gated app context for plugin code."""

    plugin_id: str
    capabilities: set[PluginCapability]
    host: PluginHostApi
    settings: PluginSettingsStore

    def has_capability(self, capability: PluginCapability) -> bool:
        return capability in self.capabilities

    def require_capability(self, capability: PluginCapability) -> None:
        if capability not in self.capabilities:
            raise PermissionError(
                f"Plugin {self.plugin_id!r} requires capability {capability.value!r}."
            )

    def selected_paths(self) -> list[Path]:
        self.require_capability(PluginCapability.LIBRARY_READ)
        return self.host.get_selected_paths()

    def show_status(self, message: str, timeout_ms: int = 2500) -> None:
        self.host.show_status_message(message, timeout_ms)

    def get_setting(self, key: str, default: object | None = None) -> object:
        return self.settings.plugin_get_setting(self.plugin_id, key, default)

    def set_setting(self, key: str, value: object) -> None:
        self.settings.plugin_set_setting(self.plugin_id, key, value)

    def on_event(self, event: PluginEvent) -> None:
        """Optional helper for plugins that want to forward events manually."""
        _ = event
