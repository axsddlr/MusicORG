"""Plugin framework models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PluginValidationError(ValueError):
    """Raised when a plugin package fails validation."""


class PluginCapability(str, Enum):
    """Declared capabilities that gate plugin API access."""

    UI_SIDEBAR_PAGE = "ui.sidebar_page"
    UI_TOOL_ACTION = "ui.tool_action"
    UI_STATUS_STRIP_CARD = "ui.status_strip_card"
    LIBRARY_READ = "library.read"
    LIBRARY_WRITE_TAGS = "library.write_tags"
    AUDIO_OUTPUT = "audio.output"
    WORKER_BACKGROUND = "worker.background"
    NETWORK_HTTP = "network.http"


class PluginState(str, Enum):
    """Lifecycle states tracked by the registry."""

    DISCOVERED = "discovered"
    DISABLED = "disabled"
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PluginManifest:
    """Validated plugin metadata from manifest.json."""

    schema_version: str
    plugin_id: str
    name: str
    version: str
    author: str
    description: str
    target_app_min: str
    entrypoint: str
    capabilities: tuple[PluginCapability, ...]
    ui: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PluginDescriptor:
    """Discovery result for a plugin package directory."""

    manifest: PluginManifest
    source_dir: Path
    entry_module: str
    entry_class: str
    is_builtin: bool


@dataclass(slots=True)
class PluginRecord:
    """Mutable runtime state for an installed plugin."""

    descriptor: PluginDescriptor
    enabled: bool
    state: PluginState = PluginState.DISCOVERED
    plugin_instance: object | None = None
    error: str = ""
    crash_count: int = 0
    startup_duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class PluginSummary:
    """UI-friendly installed plugin metadata and status."""

    plugin_id: str
    name: str
    version: str
    author: str
    description: str
    capabilities: tuple[str, ...]
    source_dir: Path
    is_builtin: bool
    enabled: bool
    state: PluginState
    error: str
    crash_count: int


@dataclass(frozen=True, slots=True)
class PluginLoadResult:
    """Result for a single plugin startup attempt."""

    plugin_id: str
    state: PluginState
    error: str = ""
    startup_duration_ms: int = 0


def capability_names(capabilities: tuple[PluginCapability, ...]) -> tuple[str, ...]:
    """Serialize capabilities to stable string names."""
    return tuple(cap.value for cap in capabilities)


def coerce_capabilities(values: list[str]) -> tuple[PluginCapability, ...]:
    """Parse and validate manifest capability strings."""
    parsed: list[PluginCapability] = []
    for raw in values:
        try:
            parsed.append(PluginCapability(raw))
        except ValueError as exc:
            raise PluginValidationError(f"Unknown capability: {raw!r}") from exc
    # Deduplicate while preserving order.
    seen: set[PluginCapability] = set()
    ordered: list[PluginCapability] = []
    for capability in parsed:
        if capability in seen:
            continue
        seen.add(capability)
        ordered.append(capability)
    return tuple(ordered)


def to_mapping(raw: object) -> dict[str, Any]:
    """Normalize unknown mapping-like payloads into plain dict[str, Any]."""
    if not isinstance(raw, dict):
        return {}
    result: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(key, str):
            result[key] = value
    return result
