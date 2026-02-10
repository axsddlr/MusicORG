"""Main application window with tabbed interface."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QMenuBar, QStatusBar, QTabWidget,
)

from musicorg.ui.autotag_panel import AutoTagPanel
from musicorg.ui.settings_dialog import SettingsDialog
from musicorg.ui.source_panel import SourcePanel
from musicorg.ui.sync_panel import SyncPanel
from musicorg.ui.tag_editor_panel import TagEditorPanel

if TYPE_CHECKING:
    from musicorg.config.settings import AppSettings


class MainWindow(QMainWindow):
    """Main application window with 4 tabs."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self._settings = settings

        self.setWindowTitle("MusicOrg")
        self.setMinimumSize(900, 600)
        self.resize(1100, 750)

        self._setup_tabs()
        self._setup_menu()
        self._setup_statusbar()
        self._connect_panels()
        self._restore_state()

    def _setup_tabs(self) -> None:
        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        self._source_panel = SourcePanel()
        self._tag_editor_panel = TagEditorPanel()
        self._autotag_panel = AutoTagPanel()
        self._sync_panel = SyncPanel()

        self._tabs.addTab(self._source_panel, "Source")
        self._tabs.addTab(self._tag_editor_panel, "Tag Editor")
        self._tabs.addTab(self._autotag_panel, "Auto-Tag")
        self._tabs.addTab(self._sync_panel, "Sync")

        # Apply saved dirs
        if self._settings.source_dir:
            self._source_panel.set_source_dir(self._settings.source_dir)
            self._sync_panel.set_source_dir(self._settings.source_dir)
        if self._settings.dest_dir:
            self._sync_panel.set_dest_dir(self._settings.dest_dir)
        self._sync_panel.set_path_format(self._settings.path_format)

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

    def _setup_statusbar(self) -> None:
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("Ready")

    def _connect_panels(self) -> None:
        # Source → Tag Editor: send selected files
        self._source_panel.connect_send_to_editor(self._send_to_editor)
        # Source → Auto-Tag: send selected files
        self._source_panel.connect_send_to_autotag(self._send_to_autotag)
        # Auto-Tag applied → refresh notice
        self._autotag_panel.tags_applied.connect(
            lambda: self._statusbar.showMessage("Tags applied — re-scan to see changes")
        )

    def _send_to_editor(self, paths: list[Path]) -> None:
        if paths:
            self._tag_editor_panel.load_files(paths)
            self._tabs.setCurrentWidget(self._tag_editor_panel)

    def _send_to_autotag(self, paths: list[Path]) -> None:
        if paths:
            self._autotag_panel.load_files(paths)
            self._tabs.setCurrentWidget(self._autotag_panel)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec():
            # Re-apply settings
            if self._settings.source_dir:
                self._source_panel.set_source_dir(self._settings.source_dir)
                self._sync_panel.set_source_dir(self._settings.source_dir)
            if self._settings.dest_dir:
                self._sync_panel.set_dest_dir(self._settings.dest_dir)
            self._sync_panel.set_path_format(self._settings.path_format)
            self._statusbar.showMessage("Settings updated")

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
        self._settings.window_geometry = self.saveGeometry()
        super().closeEvent(event)
