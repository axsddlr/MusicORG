"""Construct every top-level panel/dialog offscreen to catch constructor-time crashes."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from musicorg.config.settings import AppSettings
from musicorg.core.library_db import LibraryDatabase
from musicorg.plugins.runtime import PluginRuntime
from musicorg.runtime_paths import builtin_themes_root
from musicorg.ui.artwork_downloader_panel import ArtworkDownloaderPanel
from musicorg.ui.autotag_panel import AutoTagPanel
from musicorg.ui.batch_metadata_dialog import BatchMetadataDialog
from musicorg.ui.batch_rename_dialog import BatchRenameDialog
from musicorg.ui.duplicates_panel import DuplicatesPanel
from musicorg.ui.keybindings import DEFAULT_KEYBINDS, KeybindRegistry
from musicorg.ui.library_tools_dialog import LibraryToolsDialog
from musicorg.ui.main_window import MainWindow
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
from musicorg.ui.themes.registry import ThemeRegistry
from musicorg.ui.themes.service import ThemeService


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    s = AppSettings.__new__(AppSettings)
    s._qs = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    return s


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    p = tmp_path / "song.mp3"
    p.write_bytes(b"audio")
    return p


@pytest.fixture
def theme_service(settings: AppSettings, tmp_path: Path) -> ThemeService:
    registry = ThemeRegistry(builtin_root=builtin_themes_root(), user_root=tmp_path / "themes")
    service = ThemeService(QApplication.instance(), settings, registry)
    service.reload_themes()
    return service


@pytest.fixture
def library_db(tmp_path: Path):
    db = LibraryDatabase(tmp_path / "lib.db")
    db.open()
    yield db
    db.close()


# name -> factory(ctx, audio); ctx carries fixtures
def _factories():
    return {
        "ArtworkDownloaderPanel": lambda c: ArtworkDownloaderPanel(),
        "AutoTagPanel": lambda c: AutoTagPanel(),
        "BatchMetadataDialog": lambda c: BatchMetadataDialog([c.audio]),
        "BatchRenameDialog": lambda c: BatchRenameDialog([c.audio]),
        "DuplicatesPanel": lambda c: DuplicatesPanel(),
        "QuickTagPanel": lambda c: QuickTagPanel(),
        "RawFilesPanel": lambda c: RawFilesPanel(),
        "SettingsDialog": lambda c: SettingsDialog(c.settings),
        "ShortcutsDialog": lambda c: ShortcutsDialog(KeybindRegistry(DEFAULT_KEYBINDS)),
        "ShortcutEditorDialog": lambda c: ShortcutEditorDialog(
            KeybindRegistry(DEFAULT_KEYBINDS), c.settings
        ),
        "SourcePanel": lambda c: SourcePanel(),
        "SpotifyFeaturesPanel": lambda c: SpotifyFeaturesPanel(),
        "SyncPanel": lambda c: SyncPanel(),
        "TagEditorPanel": lambda c: TagEditorPanel(),
        "TemplateRenameDialog": lambda c: TemplateRenameDialog([c.audio]),
        "PluginManagerDialog": lambda c: PluginManagerDialog(
            PluginRuntime(c.settings), c.settings, lambda: None
        ),
        "ThemeDialog": lambda c: ThemeDialog(c.settings, c.theme_service),
        "LibraryToolsDialog": lambda c: LibraryToolsDialog(c.library_db),
        "MainWindow": lambda c: MainWindow(c.settings, theme_service=c.theme_service),
        "MainWindow+PluginRuntime": lambda c: MainWindow(
            c.settings,
            theme_service=c.theme_service,
            plugin_runtime=PluginRuntime(c.settings),
        ),
    }


class _Ctx:
    def __init__(self, **kw) -> None:
        self.__dict__.update(kw)


@pytest.mark.parametrize("name", list(_factories()))
def test_widget_constructs(name, qtbot, settings, audio, theme_service, library_db) -> None:
    ctx = _Ctx(settings=settings, audio=audio, theme_service=theme_service, library_db=library_db)
    widget = _factories()[name](ctx)
    qtbot.addWidget(widget)
    if hasattr(widget, "load_files"):
        widget.load_files([audio])
    if name.startswith("MainWindow"):
        # avoid closeEvent writing geometry / racing workers; just drop it
        widget.closeEvent = lambda event: None
