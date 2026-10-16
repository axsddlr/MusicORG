"""Plugin runtime orchestration and lifecycle management."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from musicorg import __version__ as APP_VERSION
from musicorg.plugins.context import PluginContext, PluginHostApi
from musicorg.plugins.hooks import BottomBarSpec, PluginEvent, SidebarPageSpec, ToolActionSpec
from musicorg.plugins.loader import PluginLoader, PluginSearchRoot
from musicorg.plugins.models import (
    PluginCapability,
    PluginLoadResult,
    PluginManifest,
    PluginRecord,
    PluginState,
)
from musicorg.plugins.registry import PluginRegistry


class PluginRuntime:
    """Discover, load, start, and stop plugins safely."""

    _AUTO_DISABLE_CRASH_THRESHOLD = 3

    def __init__(
        self,
        settings,
        *,
        builtin_root: Path | None = None,
    ) -> None:
        self._settings = settings
        self._builtin_root = builtin_root or (Path(__file__).resolve().parent / "builtin")
        self._registry = PluginRegistry(settings)
        self._host: PluginHostApi | None = None
        self._running_order: list[str] = []
        self._contexts: dict[str, PluginContext] = {}
        self._sidebar_specs: list[tuple[str, SidebarPageSpec]] = []
        self._tool_specs: list[tuple[str, ToolActionSpec]] = []
        self._bottom_specs: list[tuple[str, BottomBarSpec]] = []
        self._last_load_results: list[PluginLoadResult] = []

    @property
    def user_plugins_dir(self) -> Path:
        return self._settings.plugins_dir_path

    @property
    def safe_mode_enabled(self) -> bool:
        return self._settings.plugins_safe_mode

    def available_plugins(self):
        return self._registry.summaries()

    def load_errors(self) -> list[str]:
        return self._registry.load_errors()

    def sidebar_page_entries(self) -> list[tuple[str, SidebarPageSpec]]:
        return list(self._sidebar_specs)

    def tool_action_entries(self) -> list[tuple[str, ToolActionSpec]]:
        return list(self._tool_specs)

    def bottom_bar_entries(self) -> list[tuple[str, BottomBarSpec]]:
        return list(self._bottom_specs)

    def last_load_results(self) -> list[PluginLoadResult]:
        return list(self._last_load_results)

    def set_enabled(self, plugin_id: str, enabled: bool) -> bool:
        return self._registry.set_enabled(plugin_id, enabled)

    def start(self, host: PluginHostApi) -> list[str]:
        """Discover and start all enabled plugins for the host session."""
        self._host = host
        self._discover()
        self._start_enabled_plugins()
        return self.load_errors()

    def reload(self) -> list[str]:
        """Reload plugins using existing host binding."""
        self.shutdown()
        host = self._host
        if host is None:
            self._discover()
            return self.load_errors()
        return self.start(host)

    def shutdown(self) -> None:
        """Stop and dispose running plugins in reverse startup order."""
        self.emit_event("app.shutting_down", {})
        for plugin_id in list(reversed(self._running_order)):
            record = self._registry.get_record(plugin_id)
            if record is None or record.plugin_instance is None:
                continue
            instance = record.plugin_instance
            try:
                self._safe_call(plugin_id, "stop", getattr(instance, "stop"))
            except Exception as exc:
                self._registry.append_error(f"{plugin_id}: stop failed: {exc}")
            try:
                self._safe_call(plugin_id, "dispose", getattr(instance, "dispose"))
            except Exception as exc:
                self._registry.append_error(f"{plugin_id}: dispose failed: {exc}")
            record.plugin_instance = None
            record.state = PluginState.STOPPED if record.enabled else PluginState.DISABLED
        self._running_order = []
        self._contexts = {}
        self._sidebar_specs = []
        self._tool_specs = []
        self._bottom_specs = []

    def emit_event(self, name: str, payload: dict[str, object]) -> None:
        """Emit an event to all running plugins with optional on_event hooks."""
        event = PluginEvent(name=name, payload=payload)
        for plugin_id in list(self._running_order):
            record = self._registry.get_record(plugin_id)
            if record is None or record.plugin_instance is None:
                continue
            callback = getattr(record.plugin_instance, "on_event", None)
            if callback is None:
                continue
            try:
                self._safe_call(plugin_id, f"on_event({name})", lambda: callback(event))
            except Exception as exc:
                self._registry.append_error(f"{plugin_id}: event handler failed: {exc}")
                self._fail_plugin(record, f"on_event failed: {exc}", stop_instance=True)

    def _discover(self) -> None:
        loader = PluginLoader(
            [
                PluginSearchRoot(path=self._builtin_root, is_builtin=True),
                PluginSearchRoot(path=self.user_plugins_dir, is_builtin=False),
            ],
            allow_symlinks=False,
        )
        descriptors, errors = loader.discover()
        self._loader = loader
        self._registry.set_discovered(descriptors, errors)
        self._last_load_results = []

    def _start_enabled_plugins(self) -> None:
        self._running_order = []
        self._contexts = {}
        self._sidebar_specs = []
        self._tool_specs = []
        self._bottom_specs = []
        self._registry.clear_runtime_state()

        host = self._host
        if host is None:
            return
        for record in self._registry.iter_enabled():
            result = self._start_record(record, host)
            self._last_load_results.append(result)

    def _start_record(self, record: PluginRecord, host: PluginHostApi) -> PluginLoadResult:
        manifest = record.descriptor.manifest
        plugin_id = manifest.plugin_id

        if self.safe_mode_enabled and not record.descriptor.is_builtin:
            record.state = PluginState.DISABLED
            record.error = "Disabled by safe mode"
            return PluginLoadResult(plugin_id=plugin_id, state=record.state, error=record.error)

        if not self._is_app_version_compatible(manifest):
            error = (
                f"Requires app >= {manifest.target_app_min}; "
                f"current version is {APP_VERSION}"
            )
            self._fail_plugin(record, error, stop_instance=False, count_crash=False)
            return PluginLoadResult(plugin_id=plugin_id, state=record.state, error=record.error)

        try:
            instance = self._loader.load_entrypoint(record.descriptor)
        except Exception as exc:
            self._fail_plugin(record, f"Entrypoint load failed: {exc}", stop_instance=False)
            return PluginLoadResult(plugin_id=plugin_id, state=record.state, error=record.error)

        missing = [
            method_name
            for method_name in ("initialize", "start", "stop", "dispose")
            if not callable(getattr(instance, method_name, None))
        ]
        if missing:
            self._fail_plugin(
                record,
                f"Entrypoint missing required methods: {', '.join(missing)}",
                stop_instance=False,
            )
            return PluginLoadResult(plugin_id=plugin_id, state=record.state, error=record.error)

        record.plugin_instance = instance
        record.state = PluginState.STARTING
        context = PluginContext(
            plugin_id=plugin_id,
            capabilities=set(manifest.capabilities),
            host=host,
            settings=self._settings,
        )
        self._contexts[plugin_id] = context

        startup_ms = 0
        try:
            startup_ms += self._safe_call(plugin_id, "initialize", lambda: instance.initialize(context))
            startup_ms += self._safe_call(plugin_id, "start", instance.start)
            self._collect_sidebar_pages(record)
            self._collect_tool_actions(record)
            self._collect_bottom_bars(record)
        except Exception as exc:
            self._fail_plugin(record, f"Startup failed: {exc}", stop_instance=True)
            return PluginLoadResult(plugin_id=plugin_id, state=record.state, error=record.error)

        record.state = PluginState.RUNNING
        record.error = ""
        record.startup_duration_ms = startup_ms
        self._running_order.append(plugin_id)
        self._registry.reset_crash_count(plugin_id)
        return PluginLoadResult(
            plugin_id=plugin_id,
            state=record.state,
            startup_duration_ms=startup_ms,
        )

    def _collect_sidebar_pages(self, record: PluginRecord) -> None:
        plugin_id = record.descriptor.manifest.plugin_id
        instance = record.plugin_instance
        if instance is None:
            return
        callback = getattr(instance, "register_sidebar_pages", None)
        if callback is None:
            return
        if PluginCapability.UI_SIDEBAR_PAGE not in record.descriptor.manifest.capabilities:
            raise PermissionError(
                "register_sidebar_pages requires capability 'ui.sidebar_page'"
            )
        value = callback()
        if value is None:
            return
        if not isinstance(value, list):
            raise TypeError("register_sidebar_pages must return list[SidebarPageSpec]")
        for item in value:
            if not isinstance(item, SidebarPageSpec):
                raise TypeError("register_sidebar_pages must return list[SidebarPageSpec]")
            self._sidebar_specs.append((plugin_id, item))

    def _collect_tool_actions(self, record: PluginRecord) -> None:
        plugin_id = record.descriptor.manifest.plugin_id
        instance = record.plugin_instance
        if instance is None:
            return
        callback = getattr(instance, "register_tools_actions", None)
        if callback is None:
            return
        if PluginCapability.UI_TOOL_ACTION not in record.descriptor.manifest.capabilities:
            raise PermissionError(
                "register_tools_actions requires capability 'ui.tool_action'"
            )
        value = callback()
        if value is None:
            return
        if not isinstance(value, list):
            raise TypeError("register_tools_actions must return list[ToolActionSpec]")
        for item in value:
            if not isinstance(item, ToolActionSpec):
                raise TypeError("register_tools_actions must return list[ToolActionSpec]")
            self._tool_specs.append((plugin_id, item))

    def _collect_bottom_bars(self, record: PluginRecord) -> None:
        plugin_id = record.descriptor.manifest.plugin_id
        instance = record.plugin_instance
        if instance is None:
            return
        callback = getattr(instance, "register_bottom_bars", None)
        if callback is None:
            return
        if PluginCapability.UI_STATUS_STRIP_CARD not in record.descriptor.manifest.capabilities:
            raise PermissionError(
                "register_bottom_bars requires capability 'ui.status_strip_card'"
            )
        value = callback()
        if value is None:
            return
        if not isinstance(value, list):
            raise TypeError("register_bottom_bars must return list[BottomBarSpec]")
        for item in value:
            if not isinstance(item, BottomBarSpec):
                raise TypeError("register_bottom_bars must return list[BottomBarSpec]")
            self._bottom_specs.append((plugin_id, item))

    def _safe_call(self, plugin_id: str, phase: str, func: Callable[[], None]) -> int:
        start = time.monotonic()
        func()
        elapsed_ms = int((time.monotonic() - start) * 1000)
        timeout_ms = max(250, int(self._settings.plugin_startup_timeout_ms))
        if phase in {"initialize", "start"} and elapsed_ms > timeout_ms:
            raise TimeoutError(
                f"{phase} took {elapsed_ms}ms (limit {timeout_ms}ms)"
            )
        return elapsed_ms

    def _fail_plugin(
        self,
        record: PluginRecord,
        message: str,
        *,
        stop_instance: bool,
        count_crash: bool = True,
    ) -> None:
        plugin_id = record.descriptor.manifest.plugin_id
        record.error = message
        record.state = PluginState.FAILED
        self._registry.append_error(f"{plugin_id}: {message}")

        if stop_instance and record.plugin_instance is not None:
            try:
                stop_fn = getattr(record.plugin_instance, "stop", None)
                if callable(stop_fn):
                    stop_fn()
            except Exception:
                pass
            try:
                dispose_fn = getattr(record.plugin_instance, "dispose", None)
                if callable(dispose_fn):
                    dispose_fn()
            except Exception:
                pass
            record.plugin_instance = None

        self._running_order = [item for item in self._running_order if item != plugin_id]
        self._sidebar_specs = [item for item in self._sidebar_specs if item[0] != plugin_id]
        self._tool_specs = [item for item in self._tool_specs if item[0] != plugin_id]
        self._bottom_specs = [item for item in self._bottom_specs if item[0] != plugin_id]
        self._contexts.pop(plugin_id, None)

        if not count_crash:
            return

        crashes = self._registry.increment_crash(plugin_id)
        if crashes >= self._AUTO_DISABLE_CRASH_THRESHOLD and not record.descriptor.is_builtin:
            self._registry.set_enabled(plugin_id, False)
            record.state = PluginState.DISABLED
            record.error = f"{message} (auto-disabled after {crashes} crashes)"
            self._registry.append_error(f"{plugin_id}: auto-disabled after repeated crashes")

    @staticmethod
    def _is_app_version_compatible(manifest: PluginManifest) -> bool:
        return PluginRuntime._parse_semver(APP_VERSION) >= PluginRuntime._parse_semver(
            manifest.target_app_min
        )

    @staticmethod
    def _parse_semver(value: str) -> tuple[int, int, int]:
        raw = value.split("-", 1)[0].split("+", 1)[0]
        parts = raw.split(".")
        if len(parts) < 3:
            return (0, 0, 0)
        parsed: list[int] = []
        for part in parts[:3]:
            try:
                parsed.append(int(part))
            except ValueError:
                parsed.append(0)
        return tuple(parsed[:3])  # type: ignore[return-value]
