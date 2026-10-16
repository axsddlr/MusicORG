"""Plugin registry for installed metadata and runtime state."""

from __future__ import annotations

from collections.abc import Iterable

from musicorg.plugins.models import (
    PluginDescriptor,
    PluginRecord,
    PluginState,
    PluginSummary,
    capability_names,
)


class PluginRegistry:
    """Tracks discovered plugins, enablement, and runtime state."""

    def __init__(self, settings) -> None:
        self._settings = settings
        self._records: dict[str, PluginRecord] = {}
        self._errors: list[str] = []

    def set_discovered(self, descriptors: list[PluginDescriptor], discovery_errors: list[str]) -> None:
        enabled_map = self._settings.plugin_enabled_map
        crash_counts = self._settings.plugin_crash_counters
        self._errors = list(discovery_errors)
        self._records = {}

        for descriptor in descriptors:
            plugin_id = descriptor.manifest.plugin_id
            enabled_default = True
            enabled = bool(enabled_map.get(plugin_id, enabled_default))
            record = PluginRecord(
                descriptor=descriptor,
                enabled=enabled,
                state=PluginState.DISCOVERED if enabled else PluginState.DISABLED,
                crash_count=max(0, int(crash_counts.get(plugin_id, 0))),
            )
            self._records[plugin_id] = record

    def iter_records(self) -> Iterable[PluginRecord]:
        return self._records.values()

    def iter_enabled(self) -> Iterable[PluginRecord]:
        for record in self._records.values():
            if record.enabled:
                yield record

    def get_record(self, plugin_id: str) -> PluginRecord | None:
        return self._records.get(plugin_id)

    def set_enabled(self, plugin_id: str, enabled: bool) -> bool:
        record = self._records.get(plugin_id)
        if record is None:
            return False
        record.enabled = enabled
        record.state = PluginState.DISCOVERED if enabled else PluginState.DISABLED
        if not enabled:
            record.plugin_instance = None
        enabled_map = self._settings.plugin_enabled_map
        enabled_map[plugin_id] = enabled
        self._settings.plugin_enabled_map = enabled_map
        return True

    def set_error(self, plugin_id: str, message: str) -> None:
        record = self._records.get(plugin_id)
        if record is None:
            self._errors.append(message)
            return
        record.state = PluginState.FAILED
        record.error = message

    def clear_runtime_state(self) -> None:
        for record in self._records.values():
            if not record.enabled:
                record.state = PluginState.DISABLED
                record.plugin_instance = None
                continue
            record.state = PluginState.DISCOVERED
            record.plugin_instance = None
            record.error = ""
            record.startup_duration_ms = 0

    def increment_crash(self, plugin_id: str) -> int:
        record = self._records.get(plugin_id)
        if record is None:
            return 0
        record.crash_count += 1
        counters = self._settings.plugin_crash_counters
        counters[plugin_id] = record.crash_count
        self._settings.plugin_crash_counters = counters
        return record.crash_count

    def reset_crash_count(self, plugin_id: str) -> None:
        record = self._records.get(plugin_id)
        if record is None:
            return
        record.crash_count = 0
        counters = self._settings.plugin_crash_counters
        counters[plugin_id] = 0
        self._settings.plugin_crash_counters = counters

    def append_error(self, message: str) -> None:
        self._errors.append(message)

    def load_errors(self) -> list[str]:
        errors = list(self._errors)
        for record in self._records.values():
            if record.error:
                errors.append(f"{record.descriptor.manifest.plugin_id}: {record.error}")
        return errors

    def summaries(self) -> list[PluginSummary]:
        entries = [
            PluginSummary(
                plugin_id=record.descriptor.manifest.plugin_id,
                name=record.descriptor.manifest.name,
                version=record.descriptor.manifest.version,
                author=record.descriptor.manifest.author,
                description=record.descriptor.manifest.description,
                capabilities=capability_names(record.descriptor.manifest.capabilities),
                source_dir=record.descriptor.source_dir,
                is_builtin=record.descriptor.is_builtin,
                enabled=record.enabled,
                state=record.state,
                error=record.error,
                crash_count=record.crash_count,
            )
            for record in self._records.values()
        ]
        return sorted(entries, key=lambda item: item.name.lower())
