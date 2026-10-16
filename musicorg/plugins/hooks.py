"""Plugin extension hook contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Protocol

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from musicorg.plugins.context import PluginContext


@dataclass(frozen=True, slots=True)
class SidebarPageSpec:
    """Sidebar page contribution metadata."""

    page_id: str
    title: str
    widget_factory: Callable[[QWidget | None], QWidget]
    icon: str = "\u25ba"
    order: int = 100


@dataclass(frozen=True, slots=True)
class ToolActionSpec:
    """Tools menu contribution metadata."""

    action_id: str
    text: str
    callback: Callable[[], None]
    requires_selection: bool = True


@dataclass(frozen=True, slots=True)
class BottomBarSpec:
    """Bottom bar contribution metadata."""

    bar_id: str
    widget_factory: Callable[[QWidget | None], QWidget]
    order: int = 100


@dataclass(frozen=True, slots=True)
class ShortcutSpec:
    """Optional keyboard shortcut contribution."""

    shortcut_id: str
    text: str
    callback: Callable[[], None]
    sequence: str
    requires_selection: bool = False


@dataclass(frozen=True, slots=True)
class PluginEvent:
    """Typed runtime event emitted to plugins."""

    name: str
    payload: dict[str, object] = field(default_factory=dict)


class PluginLifecycle(Protocol):
    """Required lifecycle contract for plugin entrypoint classes."""

    def initialize(self, context: PluginContext) -> None:
        """Attach plugin context and allocate resources."""

    def start(self) -> None:
        """Start plugin runtime behavior after initialization."""

    def stop(self) -> None:
        """Stop runtime activity before application shutdown/reload."""

    def dispose(self) -> None:
        """Release resources and disconnect signal handlers."""
