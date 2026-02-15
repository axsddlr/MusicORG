"""Main application window with sidebar navigation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget,
)

from musicorg.ui.autotag_panel import AutoTagPanel
from musicorg.ui.artwork_downloader_panel import ArtworkDownloaderPanel
from musicorg.ui.duplicates_panel import DuplicatesPanel
from musicorg.ui.keybindings import (
    DEFAULT_KEYBINDS,
    KeybindConflictError,
    KeybindRegistry,
    create_bound_action,
)
from musicorg.ui.settings_dialog import SettingsDialog
from musicorg.ui.shortcuts_dialog import ShortcutsDialog
from musicorg.ui.source_panel import SourcePanel
from musicorg.ui.sync_panel import SyncPanel
from musicorg.ui.tag_editor_panel import TagEditorPanel
from musicorg.ui.widgets.artwork_backdrop import ArtworkBackdrop
from musicorg.ui.widgets.sidebar import SidebarNav
from musicorg.ui.widgets.status_strip import StatusStrip

if TYPE_CHECKING:
    from musicorg.config.settings import AppSettings


class MainWindow(QMainWindow):
    """Main application window with sidebar navigation."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self._settings = settings
        self._tag_editor_action: QAction | None = None
        self._autotag_action: QAction | None = None
        self._artwork_action: QAction | None = None
        try:
            self._keybind_registry = KeybindRegistry(
                DEFAULT_KEYBINDS,
                self._settings.keybind_overrides,
            )
        except (KeybindConflictError, ValueError):
            self._settings.keybind_overrides = {}
            self._keybind_registry = KeybindRegistry(DEFAULT_KEYBINDS)

        self.setWindowTitle("MusicOrg")
        self.setMinimumSize(900, 600)
        self.resize(1100, 750)
        self.setObjectName("MainWindow")

        self._setup_layout()
        self._setup_menu()
        self._connect_panels()
        self._restore_state()

    def _setup_layout(self) -> None:
        central = QWidget()
        central.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Main content row: sidebar + stacked panels
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)

        self._sidebar = SidebarNav()
        self._sidebar.page_changed.connect(self._on_nav_changed)
        content_row.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._source_panel = SourcePanel()
        self._source_panel.set_album_artwork_selection_mode(
            self._settings.album_artwork_selection_mode
        )
        self._sync_panel = SyncPanel()
        self._duplicates_panel = DuplicatesPanel()

        # Tag Editor, Auto-Tag, and Artwork Downloader are popup dialogs.
        self._tag_editor_panel = TagEditorPanel(self)
        self._autotag_panel = AutoTagPanel(self)
        self._artwork_downloader_panel = ArtworkDownloaderPanel(self)

        cache_path = self._settings.tag_cache_db_path
        self._source_panel.set_cache_db_path(cache_path)
        self._tag_editor_panel.set_cache_db_path(cache_path)
        self._autotag_panel.set_cache_db_path(cache_path)
        self._artwork_downloader_panel.set_cache_db_path(cache_path)
        self._autotag_panel.set_discogs_token(self._settings.discogs_token)
        self._artwork_downloader_panel.set_discogs_token(self._settings.discogs_token)
        self._duplicates_panel.set_cache_db_path(cache_path)

        self._stack.addWidget(self._source_panel)      # index 0
        self._stack.addWidget(self._sync_panel)         # index 1
        self._stack.addWidget(self._duplicates_panel)   # index 2
        self._content_container = QWidget()
        content_grid = QGridLayout(self._content_container)
        content_grid.setContentsMargins(0, 0, 0, 0)
        content_grid.setSpacing(0)
        content_grid.addWidget(self._stack, 0, 0)
        self._backdrop = ArtworkBackdrop()
        self._backdrop.set_opacity(self._settings.backdrop_opacity)
        content_grid.addWidget(self._backdrop, 0, 0)
        self._backdrop.raise_()
        content_row.addWidget(self._content_container, 1)

        outer.addLayout(content_row, 1)

        # Status strip
        self._status_strip = StatusStrip()
        outer.addWidget(self._status_strip)

        # Apply saved dirs
        if self._settings.source_dir:
            self._source_panel.set_source_dir(self._settings.source_dir)
            self._sync_panel.set_source_dir(self._settings.source_dir)
            self._duplicates_panel.set_source_dir(self._settings.source_dir)
        if self._settings.dest_dir:
            self._sync_panel.set_dest_dir(self._settings.dest_dir)
        self._sync_panel.set_path_format(self._settings.path_format)

    def _on_nav_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        if index == 0:
            self._source_panel.emit_active_artist_artwork()
        else:
            self._backdrop.clear()

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        exit_action = create_bound_action(
            parent=self,
            text="E&xit",
            keybind_id="app.exit",
            registry=self._keybind_registry,
            handler=self.close,
        )
        file_menu.addAction(exit_action)

        # Settings menu
        settings_menu = menubar.addMenu("&Settings")
        prefs_action = create_bound_action(
            parent=self,
            text="&Preferences...",
            keybind_id="app.preferences",
            registry=self._keybind_registry,
            handler=self._open_settings,
        )
        settings_menu.addAction(prefs_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        self._tag_editor_action = create_bound_action(
            parent=self,
            text="Open &Tag Editor",
            keybind_id="tools.open_tag_editor",
            registry=self._keybind_registry,
            handler=self._open_tag_editor_from_selection,
        )
        tools_menu.addAction(self._tag_editor_action)
        self._autotag_action = create_bound_action(
            parent=self,
            text="Open &Auto-Tag",
            keybind_id="tools.open_autotag",
            registry=self._keybind_registry,
            handler=self._open_autotag_from_selection,
        )
        tools_menu.addAction(self._autotag_action)
        self._artwork_action = create_bound_action(
            parent=self,
            text="Open &Artwork Downloader",
            keybind_id="tools.open_artwork",
            registry=self._keybind_registry,
            handler=self._open_artwork_from_selection,
        )
        tools_menu.addAction(self._artwork_action)
        self._update_tools_availability(total=0, selected=0)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        shortcuts_action = create_bound_action(
            parent=self,
            text="Keyboard &Shortcuts",
            keybind_id="help.keyboard_shortcuts",
            registry=self._keybind_registry,
            handler=self._open_shortcuts,
        )
        help_menu.addAction(shortcuts_action)
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _connect_panels(self) -> None:
        # Context menu -> Tag Editor / Auto-Tag / Artwork Downloader
        self._source_panel.send_to_editor_requested.connect(self._send_to_editor)
        self._source_panel.send_to_autotag_requested.connect(self._send_to_autotag)
        self._source_panel.send_to_artwork_requested.connect(self._send_to_artwork)
        self._source_panel.selection_stats_changed.connect(self._status_strip.set_file_count)
        self._source_panel.selection_stats_changed.connect(self._update_tools_availability)
        self._source_panel.album_artwork_changed.connect(self._backdrop.set_artwork)
        self._update_tools_availability(
            total=0,
            selected=len(self._source_panel.selected_paths()),
        )
        # Auto-Tag applied -> refresh notice
        self._autotag_panel.tags_applied.connect(
            lambda: self._status_strip.show_message("Tags applied - re-scan to see changes")
        )

    def _update_tools_availability(self, total: int, selected: int) -> None:
        _ = total
        enabled = selected > 0
        if self._tag_editor_action is not None:
            self._tag_editor_action.setEnabled(enabled)
        if self._autotag_action is not None:
            self._autotag_action.setEnabled(enabled)
        if self._artwork_action is not None:
            self._artwork_action.setEnabled(enabled)

    def _send_to_editor(self, paths: list[Path]) -> None:
        if paths:
            self._tag_editor_panel.load_files(paths)
            self._tag_editor_panel.show()
            self._tag_editor_panel.raise_()

    def _send_to_autotag(self, paths: list[Path]) -> None:
        if paths:
            self._autotag_panel.load_files(paths)
            self._autotag_panel.show()
            self._autotag_panel.raise_()

    def _send_to_artwork(self, paths: list[Path]) -> None:
        if paths:
            self._artwork_downloader_panel.load_files(paths)
            self._artwork_downloader_panel.show()
            self._artwork_downloader_panel.raise_()

    def _open_tag_editor_from_selection(self) -> None:
        selected_paths = self._source_panel.selected_paths()
        if not selected_paths:
            self._status_strip.show_message("Select files in Source to open Tag Editor", 2400)
            return
        self._send_to_editor(selected_paths)

    def _open_autotag_from_selection(self) -> None:
        selected_paths = self._source_panel.selected_paths()
        if not selected_paths:
            self._status_strip.show_message("Select files in Source to open Auto-Tag", 2400)
            return
        self._send_to_autotag(selected_paths)

    def _open_artwork_from_selection(self) -> None:
        selected_paths = self._source_panel.selected_paths()
        if not selected_paths:
            self._status_strip.show_message("Select files in Source to open Artwork", 2400)
            return
        self._send_to_artwork(selected_paths)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec():
            self._autotag_panel.set_discogs_token(self._settings.discogs_token)
            self._artwork_downloader_panel.set_discogs_token(self._settings.discogs_token)
            # Re-apply settings
            if self._settings.source_dir:
                self._source_panel.set_source_dir(self._settings.source_dir)
                self._sync_panel.set_source_dir(self._settings.source_dir)
                self._duplicates_panel.set_source_dir(self._settings.source_dir)
            if self._settings.dest_dir:
                self._sync_panel.set_dest_dir(self._settings.dest_dir)
            self._sync_panel.set_path_format(self._settings.path_format)
            self._source_panel.set_album_artwork_selection_mode(
                self._settings.album_artwork_selection_mode
            )
            self._backdrop.set_opacity(self._settings.backdrop_opacity)
            self._status_strip.show_message("Settings updated")

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        from musicorg import __version__
        QMessageBox.about(
            self, "About MusicOrg",
            f"MusicOrg v{__version__}\n\n"
            "A PySide6 desktop app for MP3/FLAC library management.\n\n"
            "Features:\n"
            "  - Single-file and bulk tag editing (changed-fields apply)\n"
            "  - Auto-tagging via MusicBrainz + Discogs\n"
            "  - Artwork downloader with preview + apply to selected files\n"
            "  - Ctrl/Shift range selection and album-level artwork selection\n"
            "  - Non-destructive directory sync and duplicate review\n"
            "\nHelp:\n"
            "  - Help > Keyboard Shortcuts for keybind and selection reference"
        )

    def _open_shortcuts(self) -> None:
        dialog = ShortcutsDialog(
            self._keybind_registry,
            album_artwork_selection_mode=self._source_panel.album_artwork_selection_mode,
            parent=self,
        )
        dialog.exec()

    def _restore_state(self) -> None:
        geo = self._settings.window_geometry
        if geo:
            self.restoreGeometry(geo)

    def closeEvent(self, event) -> None:
        self._source_panel.shutdown()
        self._tag_editor_panel.shutdown()
        self._autotag_panel.shutdown()
        self._artwork_downloader_panel.shutdown()
        self._sync_panel.shutdown()
        self._duplicates_panel.shutdown()
        self._settings.window_geometry = self.saveGeometry()
        super().closeEvent(event)
