"""Preferences dialog for application settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QSlider, QVBoxLayout,
)

from musicorg.ui.widgets.dir_picker import DirPicker

if TYPE_CHECKING:
    from musicorg.config.settings import AppSettings


class SettingsDialog(QDialog):
    """Dialog for editing application preferences."""

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
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

        form.addRow("Default Source Directory:", self._source_picker)
        form.addRow("Default Destination Directory:", self._dest_picker)
        form.addRow("Discogs User Token:", self._discogs_token_edit)
        form.addRow("Path Format:", self._path_format_edit)

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
        slider_val = int(self._settings.backdrop_opacity * 100)
        self._opacity_slider.setValue(slider_val)

    def _save(self) -> None:
        self._settings.source_dir = self._source_picker.path()
        self._settings.dest_dir = self._dest_picker.path()
        self._settings.discogs_token = self._discogs_token_edit.text().strip()
        self._settings.path_format = self._path_format_edit.text().strip()
        self._settings.backdrop_opacity = self._opacity_slider.value() / 100.0
        self.accept()
