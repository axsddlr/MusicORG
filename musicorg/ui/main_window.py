"""Main application window with sidebar navigation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget,
)

from musicorg.core.library_db import LibraryDatabase
from musicorg.ui.autotag_panel import AutoTagPanel
from musicorg.ui.artwork_downloader_panel import ArtworkDownloaderPanel
from musicorg.ui.batch_metadata_dialog import BatchMetadataDialog
from musicorg.ui.duplicates_panel import DuplicatesPanel
from musicorg.ui.keybindings import (
    DEFAULT_KEYBINDS,
    KeybindConflictError,
    KeybindRegistry,
    create_bound_action,
)
from musicorg.ui.library_tools_dialog import LibraryToolsDialog
from musicorg.ui.plugins_dialog import PluginManagerDialog
from musicorg.ui.quicktag_panel import QuickTagPanel
from musicorg.ui.raw_files_panel import RawFilesPanel
from musicorg.ui.settings_dialog import SettingsDialog
from musicorg.ui.shortcuts_dialog import ShortcutsDialog
from musicorg.ui.shortcuts_editor import ShortcutEditorDialog
from musicorg.ui.source_panel import SourcePanel
from musicorg.ui.spotify_features_panel import SpotifyFeaturesPanel
from musicorg.ui.sync_panel import SyncPanel
from musicorg.ui.tag_editor_panel import TagEditorPanel
from musicorg.ui.template_rename_dialog import TemplateRenameDialog
from musicorg.ui.theme_dialog import ThemeDialog
from musicorg.ui.widgets.artwork_backdrop import ArtworkBackdrop
from musicorg.ui.widgets.sidebar import SidebarNav
from musicorg.ui.widgets.status_strip import StatusStrip

if TYPE_CHECKING:
    from musicorg.config.settings import AppSettings
    from musicorg.plugins.runtime import PluginRuntime
    from musicorg.ui.themes.service import ThemeService


class MainWindow(QMainWindow):
    """Main application window with sidebar navigation."""

    def __init__(
        self,
        settings: AppSettings,
        theme_service: ThemeService | None = None,
        plugin_runtime: PluginRuntime | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._theme_service = theme_service
        self._plugin_runtime = plugin_runtime
        self._tools_menu = None
        self._plugin_page_widgets: list[QWidget] = []
        self._plugin_tool_actions: list[tuple[QAction, bool]] = []
        self._plugin_bottom_widgets: list[QWidget] = []
        self._tag_editor_action: QAction | None = None
        self._autotag_action: QAction | None = None
        self._artwork_action: QAction | None = None
        self._batch_rename_action: QAction | None = None
        self._batch_tag_action: QAction | None = None
        self._quicktag_action: QAction | None = None
        self._spotify_features_action: QAction | None = None
        self._template_rename_action: QAction | None = None
        self._library_tools_action: QAction | None = None
        self._tag_to_filename_action: QAction | None = None
        self._customize_shortcuts_action: QAction | None = None
        self._panel_selection_stats: dict[str, tuple[int, int]] = {
            "source": (0, 0),
            "raw_files": (0, 0),
        }
        try:
            self._keybind_registry = KeybindRegistry(
                DEFAULT_KEYBINDS,
                self._settings.keybind_overrides,
            )
        except (KeybindConflictError, ValueError):
            self._settings.keybind_overrides = {}
            self._keybind_registry = KeybindRegistry(DEFAULT_KEYBINDS)

        self._library_db: LibraryDatabase | None = None
        self.setWindowTitle("MusicOrg")
        self.setMinimumSize(900, 600)
        self.resize(1100, 750)
        self.setObjectName("MainWindow")

        self._setup_layout()
        self._setup_menu()
        self._connect_panels()
        self._restore_state()
        self._reload_plugins()

    def _open_library_db(self) -> LibraryDatabase | None:
        try:
            lib = LibraryDatabase(self._settings.library_db_path)
            lib.open()
            return lib
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed to open library database: %s", e)
            return None

    def _setup_layout(self) -> None:
        central = QWidget()
        central.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)

        self._sidebar = SidebarNav()
        self._sidebar.page_changed.connect(self._on_nav_changed)
        content_row.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._library_db = self._open_library_db()
        self._source_panel = SourcePanel()
        self._source_panel.set_library_db(self._library_db)
        self._source_panel.set_album_artwork_selection_mode(
            self._settings.album_artwork_selection_mode
        )
        self._sync_panel = SyncPanel()
        self._duplicates_panel = DuplicatesPanel()
        self._raw_files_panel = RawFilesPanel()

        self._tag_editor_panel = TagEditorPanel(self)
        self._autotag_panel = AutoTagPanel(self)
        self._artwork_downloader_panel = ArtworkDownloaderPanel(self)
        self._quicktag_panel = QuickTagPanel(self)
        self._spotify_features_panel = SpotifyFeaturesPanel(self)

        cache_path = self._settings.tag_cache_db_path
        identity_path = self._settings.track_identity_db_path
        self._source_panel.set_cache_db_path(cache_path)
        self._tag_editor_panel.set_cache_db_path(cache_path)
        self._tag_editor_panel.set_library_db(self._library_db)
        self._autotag_panel.set_cache_db_path(cache_path)
        self._artwork_downloader_panel.set_cache_db_path(cache_path)
        self._autotag_panel.set_discogs_token(self._settings.discogs_token)
        self._autotag_panel.set_profile_dir(self._settings.app_data_dir / "profiles")
        self._artwork_downloader_panel.set_discogs_token(self._settings.discogs_token)
        self._sync_panel.set_identity_db_path(identity_path)
        self._duplicates_panel.set_cache_db_path(cache_path)
        self._duplicates_panel.set_identity_db_path(identity_path)
        self._raw_files_panel.set_cache_db_path(cache_path)

        self._stack.addWidget(self._source_panel)
        self._stack.addWidget(self._sync_panel)
        self._stack.addWidget(self._duplicates_panel)
        self._stack.addWidget(self._raw_files_panel)
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

        self._plugin_bottom_container = QWidget()
        self._plugin_bottom_container.setObjectName("PluginBottomContainer")
        self._plugin_bottom_layout = QVBoxLayout(self._plugin_bottom_container)
        self._plugin_bottom_layout.setContentsMargins(6, 0, 6, 0)
        self._plugin_bottom_layout.setSpacing(6)
        self._plugin_bottom_container.setVisible(False)
        outer.addWidget(self._plugin_bottom_container)

        self._status_strip = StatusStrip()
        outer.addWidget(self._status_strip)

        if self._settings.source_dir:
            self._source_panel.set_source_dir(self._settings.source_dir)
            self._sync_panel.set_source_dir(self._settings.source_dir)
            self._duplicates_panel.set_source_dir(self._settings.source_dir)
            self._raw_files_panel.set_source_dir(self._settings.source_dir)
        if self._settings.dest_dir:
            self._sync_panel.set_dest_dir(self._settings.dest_dir)
        self._sync_panel.set_path_format(self._settings.path_format)

    def _on_nav_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        if index == 0:
            self._source_panel.emit_active_artist_artwork()
        else:
            self._backdrop.clear()
        self._refresh_tools_and_status_for_active_panel()

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        exit_action = create_bound_action(
            parent=self,
            text="E&xit",
            keybind_id="app.exit",
            registry=self._keybind_registry,
            handler=self.close,
        )
        file_menu.addAction(exit_action)

        settings_menu = menubar.addMenu("&Settings")
        prefs_action = create_bound_action(
            parent=self,
            text="&Preferences...",
            keybind_id="app.preferences",
            registry=self._keybind_registry,
            handler=self._open_settings,
        )
        settings_menu.addAction(prefs_action)
        select_all_action = create_bound_action(
            parent=self,
            text="Select &All Tracks",
            keybind_id="app.select_all",
            registry=self._keybind_registry,
            handler=self._select_all_tracks,
        )
        settings_menu.addAction(select_all_action)
        theme_action = QAction("&Themes...", self)
        theme_action.triggered.connect(self._open_themes)
        settings_menu.addAction(theme_action)
        plugins_action = QAction("&Plugins...", self)
        plugins_action.triggered.connect(self._open_plugins)
        settings_menu.addAction(plugins_action)

        tools_menu = menubar.addMenu("&Tools")
        self._tools_menu = tools_menu
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
        self._batch_rename_action = QAction("&Batch Rename Files...", self)
        self._batch_rename_action.triggered.connect(self._open_batch_rename_from_selection)
        tools_menu.addAction(self._batch_rename_action)

        self._template_rename_action = create_bound_action(
            parent=self,
            text="&Template Rename...",
            keybind_id="tools.open_template_rename",
            registry=self._keybind_registry,
            handler=self._open_template_rename_from_selection,
        )
        tools_menu.addAction(self._template_rename_action)

        tools_menu.addSeparator()

        self._quicktag_action = create_bound_action(
            parent=self,
            text="&Quick Tag",
            keybind_id="tools.open_quicktag",
            registry=self._keybind_registry,
            handler=self._open_quicktag_from_selection,
        )
        tools_menu.addAction(self._quicktag_action)

        self._spotify_features_action = create_bound_action(
            parent=self,
            text="Spotify &Audio Features",
            keybind_id="tools.open_spotify_features",
            registry=self._keybind_registry,
            handler=self._open_spotify_features_from_selection,
        )
        tools_menu.addAction(self._spotify_features_action)

        tools_menu.addSeparator()
        self._batch_tag_action = QAction("&Batch Tag Operations...", self)
        self._batch_tag_action.triggered.connect(self._open_batch_tag_ops)
        tools_menu.addAction(self._batch_tag_action)
        tools_menu.addSeparator()
        self._library_tools_action = QAction("&Library Tools...", self)
        self._library_tools_action.triggered.connect(self._open_library_tools)
        tools_menu.addAction(self._library_tools_action)
        self._tag_to_filename_action = QAction("Rename &Files to Match Tags...", self)
        self._tag_to_filename_action.triggered.connect(self._open_tag_to_filename)
        tools_menu.addAction(self._tag_to_filename_action)
        tools_menu.addSeparator()
        self._customize_shortcuts_action = QAction("Customize &Shortcuts...", self)
        self._customize_shortcuts_action.triggered.connect(self._open_shortcut_editor)
        tools_menu.addAction(self._customize_shortcuts_action)
        self._update_tools_availability(total=0, selected=0)

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
        self._source_panel.send_to_editor_requested.connect(self._send_to_editor)
        self._source_panel.send_to_autotag_requested.connect(self._send_to_autotag)
        self._source_panel.send_to_artwork_requested.connect(self._send_to_artwork)
        self._source_panel.selection_stats_changed.connect(
            lambda total, selected: self._on_library_selection_stats_changed(
                "source",
                total,
                selected,
            )
        )
        self._source_panel.selection_stats_changed.connect(self._on_selection_stats_changed)
        self._source_panel.scan_completed.connect(self._on_scan_completed)
        self._source_panel.album_artwork_changed.connect(self._backdrop.set_artwork)
        self._raw_files_panel.send_to_editor_requested.connect(self._send_to_editor)
        self._raw_files_panel.send_to_autotag_requested.connect(self._send_to_autotag)
        self._raw_files_panel.send_to_artwork_requested.connect(self._send_to_artwork)
        self._raw_files_panel.selection_stats_changed.connect(
            lambda total, selected: self._on_library_selection_stats_changed(
                "raw_files",
                total,
                selected,
            )
        )
        self._panel_selection_stats["source"] = (
            0,
            len(self._source_panel.selected_paths()),
        )
        self._panel_selection_stats["raw_files"] = (
            0,
            len(self._raw_files_panel.selected_paths()),
        )
        self._refresh_tools_and_status_for_active_panel()
        self._autotag_panel.tags_applied.connect(
            lambda: self._status_strip.show_message("Tags applied - re-scan to see changes")
        )
        self._quicktag_panel.tags_applied.connect(
            lambda: self._status_strip.show_message("Quick tags applied")
        )
        self._spotify_features_panel.tags_applied.connect(
            lambda: self._status_strip.show_message("Audio features applied")
        )
        if self._theme_service is not None:
            self._theme_service.theme_changed.connect(self._on_theme_changed)

    def _on_library_selection_stats_changed(
        self,
        panel_name: str,
        total: int,
        selected: int,
    ) -> None:
        self._panel_selection_stats[panel_name] = (total, selected)
        active_name = self._active_selection_panel_name()
        if active_name == panel_name:
            self._status_strip.set_file_count(total, selected)
            self._update_tools_availability(total, selected)

    def _refresh_tools_and_status_for_active_panel(self) -> None:
        active_name = self._active_selection_panel_name()
        if active_name is None:
            self._status_strip.set_file_count(0, 0)
            self._update_tools_availability(total=0, selected=0)
            return
        total, selected = self._panel_selection_stats.get(active_name, (0, 0))
        self._status_strip.set_file_count(total, selected)
        self._update_tools_availability(total=total, selected=selected)

    def _active_selection_panel_name(self) -> str | None:
        current_index = self._stack.currentIndex()
        if current_index == 0:
            return "source"
        if current_index == 3:
            return "raw_files"
        return None

    def _selected_paths_for_tools(self) -> list[Path]:
        active_name = self._active_selection_panel_name()
        if active_name == "source":
            return self._source_panel.selected_paths()
        if active_name == "raw_files":
            return self._raw_files_panel.selected_paths()
        return []

    def _active_selection_panel_label(self) -> str:
        active_name = self._active_selection_panel_name()
        if active_name == "source":
            return "Source"
        if active_name == "raw_files":
            return "Raw Files"
        return "Source or Raw Files"

    def _select_all_tracks(self) -> None:
        """Select all tracks in the currently active panel."""
        active_name = self._active_selection_panel_name()
        if active_name == "source":
            self._source_panel.select_all_visible()
        elif active_name == "raw_files":
            self._raw_files_panel.select_all_visible()
        else:
            self._status_strip.show_message("No panel active to select tracks in", 2400)

    def _update_tools_availability(self, total: int, selected: int) -> None:
        _ = total
        enabled = selected > 0
        active_name = self._active_selection_panel_name()
        if self._tag_editor_action is not None:
            self._tag_editor_action.setEnabled(enabled)
        if self._autotag_action is not None:
            self._autotag_action.setEnabled(enabled)
        if self._artwork_action is not None:
            self._artwork_action.setEnabled(enabled)
        if self._batch_rename_action is not None:
            self._batch_rename_action.setEnabled(enabled and active_name == "raw_files")
        if self._quicktag_action is not None:
            self._quicktag_action.setEnabled(enabled)
        if self._spotify_features_action is not None:
            self._spotify_features_action.setEnabled(enabled)
        if self._template_rename_action is not None:
            self._template_rename_action.setEnabled(enabled)
        for action, requires_selection in self._plugin_tool_actions:
            action.setEnabled(enabled if requires_selection else True)

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
        selected_paths = self._selected_paths_for_tools()
        if not selected_paths:
            panel_label = self._active_selection_panel_label()
            self._status_strip.show_message(
                f"Select files in {panel_label} to open Tag Editor",
                2400,
            )
            return
        self._send_to_editor(selected_paths)

    def _open_autotag_from_selection(self) -> None:
        selected_paths = self._selected_paths_for_tools()
        if not selected_paths:
            panel_label = self._active_selection_panel_label()
            self._status_strip.show_message(
                f"Select files in {panel_label} to open Auto-Tag",
                2400,
            )
            return
        self._send_to_autotag(selected_paths)

    def _open_quicktag_from_selection(self) -> None:
        selected_paths = self._selected_paths_for_tools()
        if not selected_paths:
            panel_label = self._active_selection_panel_label()
            self._status_strip.show_message(
                f"Select files in {panel_label} to open Quick Tag",
                2400,
            )
            return
        self._quicktag_panel.load_files(selected_paths)
        self._quicktag_panel.show()
        self._quicktag_panel.raise_()

    def _open_spotify_features_from_selection(self) -> None:
        selected_paths = self._selected_paths_for_tools()
        if not selected_paths:
            panel_label = self._active_selection_panel_label()
            self._status_strip.show_message(
                f"Select files in {panel_label} to open Spotify Audio Features",
                2400,
            )
            return
        self._spotify_features_panel.load_files(selected_paths)
        self._spotify_features_panel.show()
        self._spotify_features_panel.raise_()

    def _open_template_rename_from_selection(self) -> None:
        selected_paths = self._selected_paths_for_tools()
        if not selected_paths:
            panel_label = self._active_selection_panel_label()
            self._status_strip.show_message(
                f"Select files in {panel_label} to open Template Rename",
                2400,
            )
            return
        dialog = TemplateRenameDialog(selected_paths, self)
        if dialog.exec():
            rename_items = dialog.rename_items()
            if rename_items:
                # RawFilesPanel owns the rename worker lifecycle (thread quit on
                # error/cancel, shutdown, tag cache invalidation).
                self._raw_files_panel._start_batch_rename(rename_items)

    def _open_artwork_from_selection(self) -> None:
        selected_paths = self._selected_paths_for_tools()
        if not selected_paths:
            panel_label = self._active_selection_panel_label()
            self._status_strip.show_message(
                f"Select files in {panel_label} to open Artwork",
                2400,
            )
            return
        self._send_to_artwork(selected_paths)

    def _open_batch_rename_from_selection(self) -> None:
        active_name = self._active_selection_panel_name()
        if active_name != "raw_files":
            self._status_strip.show_message(
                "Batch rename is available in Raw Files.",
                2400,
            )
            return
        if not self._raw_files_panel.selected_paths():
            self._status_strip.show_message(
                "Select files in Raw Files to batch rename them.",
                2400,
            )
            return
        self._raw_files_panel.open_batch_rename_for_selection()

    def _open_batch_tag_ops(self) -> None:
        """Open batch tag operations dialog from current selection."""
        paths = self._selected_paths_for_tools()
        if not paths:
            self._status_strip.show_message(
                "Select files first to use batch tag operations.",
                2400,
            )
            return
        dialog = BatchMetadataDialog(paths, self)
        dialog.exec()

    def _open_library_tools(self) -> None:
        if self._library_db is None:
            return
        dialog = LibraryToolsDialog(self._library_db, self)
        dialog.exec()

    def _open_tag_to_filename(self) -> None:
        paths = self._selected_paths_for_tools()
        if not paths:
            self._status_strip.show_message(
                "Select files first to rename them to match tags.",
                2400,
            )
            return
        from musicorg.ui.batch_rename_dialog import BatchRenameDialog
        dialog = BatchRenameDialog(paths, parent=self)
        dialog.set_rule("$track $title")
        if dialog.exec():
            rename_items = dialog.get_rename_items()
            metadata_fields = dialog.get_metadata_fields()
            metadata_rule = dialog.rename_rule()
            self._raw_files_panel._start_batch_rename(
                rename_items,
                metadata_fields=metadata_fields,
                metadata_rule=metadata_rule,
            )

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec():
            self._autotag_panel.set_discogs_token(self._settings.discogs_token)
            self._artwork_downloader_panel.set_discogs_token(self._settings.discogs_token)
            if self._settings.source_dir:
                self._source_panel.set_source_dir(self._settings.source_dir)
                self._sync_panel.set_source_dir(self._settings.source_dir)
                self._duplicates_panel.set_source_dir(self._settings.source_dir)
                self._raw_files_panel.set_source_dir(self._settings.source_dir)
            if self._settings.dest_dir:
                self._sync_panel.set_dest_dir(self._settings.dest_dir)
            self._sync_panel.set_path_format(self._settings.path_format)
            self._source_panel.set_album_artwork_selection_mode(
                self._settings.album_artwork_selection_mode
            )
            self._backdrop.set_opacity(self._settings.backdrop_opacity)
            self._status_strip.show_message("Settings updated")

    def _open_themes(self) -> None:
        if self._theme_service is None:
            self._status_strip.show_message("Theme service is not available", 2500)
            return
        dialog = ThemeDialog(self._settings, self._theme_service, self)
        if dialog.exec():
            ok, message = self._theme_service.apply_theme(self._settings.theme_id, persist=True)
            if ok:
                self._status_strip.show_message(message, 2600)
            else:
                self._status_strip.show_message(message, 3200)

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
            "  - Raw filesystem browser with regex/text batch rename\n"
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

    def _open_shortcut_editor(self) -> None:
        dialog = ShortcutEditorDialog(self._keybind_registry, self._settings, self)
        if dialog.exec():
            old_keybinds = self._keybind_registry
            try:
                self._keybind_registry = KeybindRegistry(
                    DEFAULT_KEYBINDS,
                    self._settings.keybind_overrides,
                )
            except (KeybindConflictError, ValueError) as e:
                self._keybind_registry = old_keybinds
                QMessageBox.warning(self, "Shortcut Conflict", str(e))
                return

    def _open_plugins(self) -> None:
        if self._plugin_runtime is None:
            self._status_strip.show_message("Plugin runtime is not available", 2600)
            return
        dialog = PluginManagerDialog(
            runtime=self._plugin_runtime,
            settings=self._settings,
            on_reload_requested=self._reload_plugins,
            parent=self,
        )
        dialog.exec()

    def _reload_plugins(self) -> None:
        if self._plugin_runtime is None:
            return
        self._clear_plugin_ui_contributions()
        self._plugin_runtime.shutdown()
        self._plugin_runtime.start(self)
        self._apply_plugin_ui_contributions()
        errors = self._plugin_runtime.load_errors()
        if errors:
            self._status_strip.show_message(
                f"Plugins loaded with {len(errors)} diagnostic entries",
                4200,
            )

    def _clear_plugin_ui_contributions(self) -> None:
        for widget in self._plugin_page_widgets:
            self._stack.removeWidget(widget)
            widget.deleteLater()
        self._plugin_page_widgets = []

        for action, _requires_selection in self._plugin_tool_actions:
            if self._tools_menu is not None:
                self._tools_menu.removeAction(action)
            action.deleteLater()
        self._plugin_tool_actions = []

        for widget in self._plugin_bottom_widgets:
            self._plugin_bottom_layout.removeWidget(widget)
            widget.deleteLater()
        self._plugin_bottom_widgets = []
        self._plugin_bottom_container.setVisible(False)

    def _apply_plugin_ui_contributions(self) -> None:
        if self._plugin_runtime is None:
            return
        page_entries = sorted(
            self._plugin_runtime.sidebar_page_entries(),
            key=lambda item: (item[1].order, item[1].title.lower()),
        )
        nav_items = list(SidebarNav.BASE_ITEMS)
        for plugin_id, page_spec in page_entries:
            try:
                widget = page_spec.widget_factory(self._stack)
            except Exception as exc:
                self._status_strip.show_message(
                    f"Plugin page failed ({plugin_id}): {exc}",
                    4200,
                )
                continue
            self._plugin_page_widgets.append(widget)
            self._stack.addWidget(widget)
            nav_items.append((page_spec.icon or "\u25ba", page_spec.title))

        self._sidebar.set_items(nav_items)
        if self._stack.currentIndex() >= len(nav_items):
            self._sidebar.set_selected(0)
            self._on_nav_changed(0)
        else:
            self._sidebar.set_selected(self._stack.currentIndex())

        if self._tools_menu is not None:
            for _plugin_id, action_spec in self._plugin_runtime.tool_action_entries():
                action = QAction(action_spec.text, self)
                action.triggered.connect(action_spec.callback)
                self._tools_menu.addAction(action)
                self._plugin_tool_actions.append((action, action_spec.requires_selection))

        bottom_entries = sorted(
            self._plugin_runtime.bottom_bar_entries(),
            key=lambda item: item[1].order,
        )
        for plugin_id, bar_spec in bottom_entries:
            try:
                widget = bar_spec.widget_factory(self._plugin_bottom_container)
            except Exception as exc:
                self._status_strip.show_message(
                    f"Plugin bottom bar failed ({plugin_id}): {exc}",
                    4200,
                )
                continue
            widget.setParent(self._plugin_bottom_container)
            self._plugin_bottom_layout.addWidget(widget)
            self._plugin_bottom_widgets.append(widget)
        self._plugin_bottom_container.setVisible(bool(self._plugin_bottom_widgets))
        self._refresh_tools_and_status_for_active_panel()

    def _on_selection_stats_changed(self, total: int, selected: int) -> None:
        if self._plugin_runtime is None:
            return
        self._plugin_runtime.emit_event(
            "selection.changed",
            {"total": total, "selected": selected},
        )

    def _on_scan_completed(self, count: int) -> None:
        if self._plugin_runtime is None:
            return
        self._plugin_runtime.emit_event("scan.completed", {"count": count})

    def _on_theme_changed(self, theme_id: str) -> None:
        if self._plugin_runtime is None:
            return
        self._plugin_runtime.emit_event("theme.changed", {"theme_id": theme_id})

    # PluginHostApi surface used by PluginContext.
    def get_selected_paths(self) -> list[Path]:
        return self._selected_paths_for_tools()

    def show_status_message(self, message: str, timeout_ms: int = 2500) -> None:
        self._status_strip.show_message(message, timeout_ms)

    def _restore_state(self) -> None:
        geo = self._settings.window_geometry
        if geo:
            self.restoreGeometry(geo)

    def closeEvent(self, event) -> None:
        if self._plugin_runtime is not None:
            self._plugin_runtime.shutdown()
        self._source_panel.shutdown()
        self._tag_editor_panel.shutdown()
        self._autotag_panel.shutdown()
        self._artwork_downloader_panel.shutdown()
        self._quicktag_panel.shutdown()
        self._spotify_features_panel.shutdown()
        self._sync_panel.shutdown()
        self._duplicates_panel.shutdown()
        self._raw_files_panel.shutdown()
        if self._library_db is not None:
            try:
                self._library_db.close()
            except Exception:
                pass
        self._settings.window_geometry = self.saveGeometry()
        super().closeEvent(event)
