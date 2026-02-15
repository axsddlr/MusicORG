"""Theme management dialog."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from musicorg.ui.widgets.dir_picker import DirPicker

if TYPE_CHECKING:
    from musicorg.config.settings import AppSettings
    from musicorg.ui.themes.service import ThemeService


class ThemeDialog(QDialog):
    """Dialog for selecting and managing installed themes."""

    def __init__(
        self,
        settings: AppSettings,
        theme_service: ThemeService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._theme_service = theme_service
        self.setWindowTitle("Themes")
        self.setMinimumWidth(620)
        self._setup_ui()
        self._load()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._themes_dir_picker = DirPicker()
        self._themes_dir_picker.path_changed.connect(self._update_theme_dir_hint)
        self._themes_default_btn = QPushButton("Use Default")
        self._themes_default_btn.clicked.connect(self._use_default_themes_folder)
        self._theme_folder_btn = QPushButton("Open Folder")
        self._theme_folder_btn.clicked.connect(self._open_themes_folder)
        self._themes_dir_hint = QLabel("")
        self._themes_dir_hint.setObjectName("StatusDetail")
        self._themes_dir_hint.setWordWrap(True)

        folder_row = QHBoxLayout()
        folder_row.setContentsMargins(0, 0, 0, 0)
        folder_row.addWidget(self._themes_dir_picker, 1)
        folder_row.addWidget(self._themes_default_btn)
        folder_row.addWidget(self._theme_folder_btn)

        self._theme_combo = QComboBox()
        self._theme_combo.setMinimumContentsLength(28)
        self._theme_combo.currentIndexChanged.connect(self._update_theme_details)
        self._theme_reload_btn = QPushButton("Reload Themes")
        self._theme_reload_btn.clicked.connect(self._reload_themes)
        self._theme_details = QLabel("")
        self._theme_details.setObjectName("StatusDetail")
        self._theme_details.setWordWrap(True)

        theme_row = QHBoxLayout()
        theme_row.setContentsMargins(0, 0, 0, 0)
        theme_row.addWidget(self._theme_combo, 1)
        theme_row.addWidget(self._theme_reload_btn)

        form.addRow("Custom Themes Folder:", folder_row)
        form.addRow("", self._themes_dir_hint)
        form.addRow("Installed Themes:", theme_row)
        form.addRow("Details:", self._theme_details)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate_themes()

    def _load(self) -> None:
        self._themes_dir_picker.set_path(self._settings.theme_custom_dir)
        self._update_theme_dir_hint()
        index = self._theme_combo.findData(self._settings.theme_id)
        self._theme_combo.setCurrentIndex(max(0, index))
        self._update_theme_details()

    def _save(self) -> None:
        previous_custom_dir = self._settings.theme_custom_dir
        selected_theme_id = self._selected_theme_id()

        self._settings.theme_custom_dir = self._themes_dir_picker.path()
        if self._settings.theme_custom_dir != previous_custom_dir:
            self._theme_service.set_user_themes_dir(self._settings.themes_dir)
            errors = self._theme_service.reload_themes()
            self._populate_themes()
            index = self._theme_combo.findData(selected_theme_id)
            self._theme_combo.setCurrentIndex(max(0, index))
            if errors:
                self._show_reload_warnings(errors)

        self._settings.theme_id = self._selected_theme_id()
        self.accept()

    def _populate_themes(self) -> None:
        self._theme_combo.clear()
        for theme in self._theme_service.available_themes():
            source = "Built-in" if theme.is_builtin else "Custom"
            label = f"{theme.name} ({source})"
            self._theme_combo.addItem(label, theme.theme_id)
            details = (
                f"{theme.description}\n"
                f"Author: {theme.author} | Version: {theme.version}\n"
                f"Path: {theme.source_dir}"
            )
            self._theme_combo.setItemData(
                self._theme_combo.count() - 1,
                details,
                Qt.ItemDataRole.ToolTipRole,
            )
        if self._theme_combo.count() == 0:
            self._theme_combo.addItem("MusicOrg Default (Built-in)", "musicorg-default")

    def _reload_themes(self) -> None:
        errors = self._theme_service.reload_themes()
        current_theme_id = self._selected_theme_id()
        self._populate_themes()
        index = self._theme_combo.findData(current_theme_id)
        self._theme_combo.setCurrentIndex(max(0, index))
        self._update_theme_details()
        if errors:
            self._show_reload_warnings(errors)

    def _open_themes_folder(self) -> None:
        themes_dir = self._effective_themes_dir()
        themes_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(themes_dir)))

    def _use_default_themes_folder(self) -> None:
        self._themes_dir_picker.set_path("")
        self._update_theme_dir_hint()

    def _update_theme_dir_hint(self) -> None:
        custom = self._themes_dir_picker.path()
        effective = self._effective_themes_dir()
        if custom:
            hint = (
                f"Using custom themes folder on save: {effective}\n"
                f"Built-in themes always load from app bundle."
            )
        else:
            hint = (
                f"Using default themes folder: {effective}\n"
                f"Set a custom folder to load user themes from a different location."
            )
        self._themes_dir_hint.setText(hint)

    def _update_theme_details(self) -> None:
        details = self._theme_combo.currentData(Qt.ItemDataRole.ToolTipRole)
        if not isinstance(details, str):
            details = ""
        self._theme_details.setText(details)

    def _selected_theme_id(self) -> str:
        selected = self._theme_combo.currentData()
        if isinstance(selected, str) and selected:
            return selected
        return "musicorg-default"

    def _effective_themes_dir(self) -> Path:
        custom = self._themes_dir_picker.path()
        if custom:
            try:
                return Path(custom).expanduser()
            except OSError:
                pass
        return self._settings.default_themes_dir

    def _show_reload_warnings(self, errors: list[str]) -> None:
        preview = "\n".join(f"- {item}" for item in errors[:6])
        if len(errors) > 6:
            preview += f"\n... and {len(errors) - 6} more"
        QMessageBox.warning(self, "Theme Load Warnings", preview)
