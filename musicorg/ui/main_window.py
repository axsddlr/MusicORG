"""Main application window with sidebar navigation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget,
)

from musicorg.ui.autotag_panel import AutoTagPanel
from musicorg.ui.duplicates_panel import DuplicatesPanel
from musicorg.ui.settings_dialog import SettingsDialog
from musicorg.ui.source_panel import SourcePanel
from musicorg.ui.sync_panel import SyncPanel
from musicorg.ui.tag_editor_panel import TagEditorPanel
from musicorg.ui.widgets.sidebar import SidebarNav
from musicorg.ui.widgets.status_strip import StatusStrip

if TYPE_CHECKING:
    from musicorg.config.settings import AppSettings


class MainWindow(QMainWindow):
    """Main application window with sidebar navigation."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self._settings = settings

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
        self._sidebar.settings_clicked.connect(self._open_settings)
        content_row.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._source_panel = SourcePanel()
        self._tag_editor_panel = TagEditorPanel()
        self._autotag_panel = AutoTagPanel()
        self._sync_panel = SyncPanel()
        self._duplicates_panel = DuplicatesPanel()
        cache_path = self._settings.tag_cache_db_path
        self._source_panel.set_cache_db_path(cache_path)
        self._tag_editor_panel.set_cache_db_path(cache_path)
        self._autotag_panel.set_cache_db_path(cache_path)
        self._duplicates_panel.set_cache_db_path(cache_path)

        self._stack.addWidget(self._source_panel)      # index 0
        self._stack.addWidget(self._tag_editor_panel)   # index 1
        self._stack.addWidget(self._autotag_panel)      # index 2
        self._stack.addWidget(self._sync_panel)         # index 3
        self._stack.addWidget(self._duplicates_panel)   # index 4
        content_row.addWidget(self._stack, 1)

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

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Settings menu
        settings_menu = menubar.addMenu("&Settings")
        prefs_action = QAction("&Preferences...", self)
        prefs_action.setShortcut("Ctrl+,")
        prefs_action.triggered.connect(self._open_settings)
        settings_menu.addAction(prefs_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _connect_panels(self) -> None:
        # Source → Tag Editor: send selected files
        self._source_panel.connect_send_to_editor(self._send_to_editor)
        # Source → Auto-Tag: send selected files
        self._source_panel.connect_send_to_autotag(self._send_to_autotag)
        self._source_panel.files_selected.connect(self._autotag_panel.load_files)
        # Auto-Tag applied → refresh notice
        self._autotag_panel.tags_applied.connect(
            lambda: self._status_strip.show_message("Tags applied — re-scan to see changes")
        )

    def _send_to_editor(self, paths: list[Path]) -> None:
        if paths:
            self._tag_editor_panel.load_files(paths)
            self._stack.setCurrentIndex(1)
            self._sidebar.set_selected(1)

    def _send_to_autotag(self, paths: list[Path]) -> None:
        if paths:
            self._autotag_panel.load_files(paths)
            self._stack.setCurrentIndex(2)
            self._sidebar.set_selected(2)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec():
            # Re-apply settings
            if self._settings.source_dir:
                self._source_panel.set_source_dir(self._settings.source_dir)
                self._sync_panel.set_source_dir(self._settings.source_dir)
                self._duplicates_panel.set_source_dir(self._settings.source_dir)
            if self._settings.dest_dir:
                self._sync_panel.set_dest_dir(self._settings.dest_dir)
            self._sync_panel.set_path_format(self._settings.path_format)
            self._status_strip.show_message("Settings updated")

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        from musicorg import __version__
        QMessageBox.about(
            self, "About MusicOrg",
            f"MusicOrg v{__version__}\n\n"
            "A PySide6 desktop UI for beets music library management.\n\n"
            "Features:\n"
            "  - ID3 tag reading/editing for MP3 and FLAC\n"
            "  - Auto-tagging via MusicBrainz + Discogs\n"
            "  - Non-destructive directory sync"
        )

    def _restore_state(self) -> None:
        geo = self._settings.window_geometry
        if geo:
            self.restoreGeometry(geo)

    def closeEvent(self, event) -> None:
        self._source_panel.shutdown()
        self._tag_editor_panel.shutdown()
        self._autotag_panel.shutdown()
        self._sync_panel.shutdown()
        self._duplicates_panel.shutdown()
        self._settings.window_geometry = self.saveGeometry()
        super().closeEvent(event)
