"""Entrypoint for Pulse player plugin."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from .player_engine import PlayerEngine
from .player_mini_bar import PlayerMiniBar
from .player_page import PlayerPage
from musicorg.plugins.context import PluginContext
from musicorg.plugins.hooks import BottomBarSpec, SidebarPageSpec, ToolActionSpec
from musicorg.plugins.models import PluginCapability


class PulsePlayerPlugin:
    """First-party music player plugin."""

    def __init__(self) -> None:
        self._context: PluginContext | None = None
        self._engine: PlayerEngine | None = None
        self._page: PlayerPage | None = None
        self._mini_bar: PlayerMiniBar | None = None

    def initialize(self, context: PluginContext) -> None:
        context.require_capability(PluginCapability.UI_SIDEBAR_PAGE)
        context.require_capability(PluginCapability.AUDIO_OUTPUT)
        context.require_capability(PluginCapability.LIBRARY_READ)
        self._context = context
        self._migrate_legacy_settings()
        self._engine = PlayerEngine(context)

    def start(self) -> None:
        # No background startup work required; engine is ready after initialize.
        return

    def stop(self) -> None:
        if self._engine is not None:
            self._engine.stop()

    def dispose(self) -> None:
        if self._page is not None:
            try:
                self._page.deleteLater()
            except RuntimeError:
                pass
            self._page = None
        if self._mini_bar is not None:
            try:
                self._mini_bar.deleteLater()
            except RuntimeError:
                pass
            self._mini_bar = None
        if self._engine is not None:
            try:
                self._engine.dispose()
            except RuntimeError:
                pass
            try:
                self._engine.deleteLater()
            except RuntimeError:
                pass
            self._engine = None
        self._context = None

    def register_sidebar_pages(self) -> list[SidebarPageSpec]:
        return [
            SidebarPageSpec(
                page_id="player",
                title="Player",
                icon="\u25B6",
                order=20,
                widget_factory=self._build_page,
            )
        ]

    def register_tools_actions(self) -> list[ToolActionSpec]:
        return [
            ToolActionSpec(
                action_id="pulse_player.add_selected_to_queue",
                text="Add Selected To &Player Queue",
                callback=self._add_selected_to_queue,
                requires_selection=True,
            )
        ]

    def register_bottom_bars(self) -> list[BottomBarSpec]:
        return [
            BottomBarSpec(
                bar_id="pulse-player.transport",
                widget_factory=self._build_mini_bar,
                order=10,
            )
        ]

    def _add_selected_to_queue(self) -> None:
        if self._engine is None or self._context is None:
            return
        added = self._engine.add_selected_paths()
        if added > 0:
            self._context.show_status(f"Added {added} track(s) to player queue", 2400)
            return
        self._context.show_status("No supported files selected for queue", 2400)

    def _build_page(self, parent: QWidget | None) -> QWidget:
        if self._engine is None or self._context is None:
            raise RuntimeError("PulsePlayerPlugin is not initialized.")
        if self._page is None:
            self._page = PlayerPage(self._engine, self._context, parent)
        elif parent is not None and self._page.parent() is not parent:
            self._page.setParent(parent)
        return self._page

    def _build_mini_bar(self, parent: QWidget | None) -> QWidget:
        if self._engine is None:
            raise RuntimeError("PulsePlayerPlugin is not initialized.")
        if self._mini_bar is None:
            self._mini_bar = PlayerMiniBar(self._engine, parent)
        elif parent is not None and self._mini_bar.parent() is not parent:
            self._mini_bar.setParent(parent)
        return self._mini_bar

    def _migrate_legacy_settings(self) -> None:
        if self._context is None:
            return
        settings = self._context.settings
        migrated_flag = self._context.get_setting("migrated_from_musicbee", False)
        if bool(migrated_flag):
            return
        keys = (
            "volume",
            "muted",
            "repeat_mode",
            "shuffle_enabled",
            "restore_queue",
            "queue_paths",
            "queue_index",
        )
        for key in keys:
            current = self._context.get_setting(key, None)
            if current is not None:
                continue
            legacy = settings.plugin_get_setting("musicbee-player", key, None)
            if legacy is None:
                continue
            self._context.set_setting(key, legacy)
        self._context.set_setting("migrated_from_musicbee", True)
