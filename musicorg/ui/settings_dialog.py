"""Preferences dialog for application settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSlider, QVBoxLayout,
)

from musicorg.ui.widgets.dir_picker import DirPicker

if TYPE_CHECKING:
    from musicorg.config.settings import AppSettings
    from musicorg.ui.themes.service import ThemeService


class SettingsDialog(QDialog):
    """Dialog for editing application preferences."""

    _ALBUM_SELECTION_MODE_ITEMS: tuple[tuple[str, str], ...] = (
        ("Single-click artwork toggles album", "single_click"),
        ("Double-click artwork toggles album", "double_click"),
        ("Off (preview only)", "none"),
    )

    def __init__(
        self,
        settings: AppSettings,
        theme_service: ThemeService | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._theme_service = theme_service
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        self._setup_ui()
        self._load()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._source_picker = DirPicker()
        self._dest_picker = DirPicker()
        self._discogs_token_edit = QLineEdit()
        self._discogs_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._path_format_edit = QLineEdit()
        self._theme_combo = QComboBox()
        self._theme_combo.setMinimumContentsLength(24)
        self._theme_reload_btn = QPushButton("Reload Themes")
        self._theme_reload_btn.clicked.connect(self._reload_themes)
        self._theme_folder_btn = QPushButton("Open Themes Folder")
        self._theme_folder_btn.clicked.connect(self._open_themes_folder)
        self._album_selection_mode_combo = QComboBox()
        for label, value in self._ALBUM_SELECTION_MODE_ITEMS:
            self._album_selection_mode_combo.addItem(label, value)
        self._populate_themes()

        theme_row = QHBoxLayout()
        theme_row.setContentsMargins(0, 0, 0, 0)
        theme_row.addWidget(self._theme_combo, 1)
        theme_row.addWidget(self._theme_reload_btn)
        theme_row.addWidget(self._theme_folder_btn)

        form.addRow("Default Source Directory:", self._source_picker)
        form.addRow("Default Destination Directory:", self._dest_picker)
        form.addRow("Discogs User Token:", self._discogs_token_edit)
        form.addRow("Path Format:", self._path_format_edit)
        form.addRow("Theme:", theme_row)
        form.addRow("Artwork Click Behavior:", self._album_selection_mode_combo)

        # Backdrop opacity slider
        slider_layout = QHBoxLayout()
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 30)
        self._opacity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._opacity_slider.setTickInterval(5)
        self._opacity_label = QLabel("7%")
        self._opacity_label.setMinimumWidth(35)
        self._opacity_slider.valueChanged.connect(
            lambda v: self._opacity_label.setText(f"{v}%")
        )
        slider_layout.addWidget(self._opacity_slider)
        slider_layout.addWidget(self._opacity_label)
        form.addRow("Artwork Background Opacity:", slider_layout)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load(self) -> None:
        self._source_picker.set_path(self._settings.source_dir)
        self._dest_picker.set_path(self._settings.dest_dir)
        self._discogs_token_edit.setText(self._settings.discogs_token)
        self._path_format_edit.setText(self._settings.path_format)
        theme_index = self._theme_combo.findData(self._settings.theme_id)
        self._theme_combo.setCurrentIndex(max(0, theme_index))
        mode = self._settings.album_artwork_selection_mode
        index = self._album_selection_mode_combo.findData(mode)
        self._album_selection_mode_combo.setCurrentIndex(max(0, index))
        slider_val = int(self._settings.backdrop_opacity * 100)
        self._opacity_slider.setValue(slider_val)

    def _save(self) -> None:
        self._settings.source_dir = self._source_picker.path()
        self._settings.dest_dir = self._dest_picker.path()
        self._settings.discogs_token = self._discogs_token_edit.text().strip()
        self._settings.path_format = self._path_format_edit.text().strip()
        selected_theme = self._theme_combo.currentData()
        self._settings.theme_id = (
            str(selected_theme) if isinstance(selected_theme, str) and selected_theme else "musicorg-default"
        )
        self._settings.album_artwork_selection_mode = str(
            self._album_selection_mode_combo.currentData()
        )
        self._settings.backdrop_opacity = self._opacity_slider.value() / 100.0
        self.accept()

    def _populate_themes(self) -> None:
        self._theme_combo.clear()
        if self._theme_service is None:
            self._theme_combo.addItem("MusicOrg Default", "musicorg-default")
            self._theme_reload_btn.setEnabled(False)
            self._theme_folder_btn.setEnabled(False)
            return

        for theme in self._theme_service.available_themes():
            source = "Built-in" if theme.is_builtin else "Custom"
            label = f"{theme.name} ({source})"
            self._theme_combo.addItem(label, theme.theme_id)
            self._theme_combo.setItemData(
                self._theme_combo.count() - 1,
                theme.description,
                Qt.ItemDataRole.ToolTipRole,
            )
        if self._theme_combo.count() == 0:
            self._theme_combo.addItem("MusicOrg Default", "musicorg-default")

    def _reload_themes(self) -> None:
        if self._theme_service is None:
            return
        errors = self._theme_service.reload_themes()
        current_theme_id = str(self._theme_combo.currentData() or "")
        self._populate_themes()
        index = self._theme_combo.findData(current_theme_id)
        self._theme_combo.setCurrentIndex(max(0, index))
        if errors:
            preview = "\n".join(f"- {item}" for item in errors[:6])
            if len(errors) > 6:
                preview += f"\n... and {len(errors) - 6} more"
            QMessageBox.warning(self, "Theme Load Warnings", preview)

    def _open_themes_folder(self) -> None:
        if self._theme_service is None:
            return
        themes_dir = self._theme_service.user_themes_dir
        themes_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(themes_dir)))
