"""Theme management dialog."""

from __future__ import annotations

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
        self.setMinimumWidth(560)
        self._setup_ui()
        self._load()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._theme_combo = QComboBox()
        self._theme_combo.setMinimumContentsLength(28)
        self._theme_combo.currentIndexChanged.connect(self._update_theme_details)
        self._theme_reload_btn = QPushButton("Reload Themes")
        self._theme_reload_btn.clicked.connect(self._reload_themes)
        self._theme_folder_btn = QPushButton("Open Themes Folder")
        self._theme_folder_btn.clicked.connect(self._open_themes_folder)
        self._theme_details = QLabel("")
        self._theme_details.setObjectName("StatusDetail")
        self._theme_details.setWordWrap(True)

        theme_row = QHBoxLayout()
        theme_row.setContentsMargins(0, 0, 0, 0)
        theme_row.addWidget(self._theme_combo, 1)
        theme_row.addWidget(self._theme_reload_btn)
        theme_row.addWidget(self._theme_folder_btn)

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
        index = self._theme_combo.findData(self._settings.theme_id)
        self._theme_combo.setCurrentIndex(max(0, index))
        self._update_theme_details()

    def _save(self) -> None:
        selected_theme = self._theme_combo.currentData()
        self._settings.theme_id = (
            str(selected_theme)
            if isinstance(selected_theme, str) and selected_theme
            else "musicorg-default"
        )
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
        current_theme_id = str(self._theme_combo.currentData() or "")
        self._populate_themes()
        index = self._theme_combo.findData(current_theme_id)
        self._theme_combo.setCurrentIndex(max(0, index))
        self._update_theme_details()
        if errors:
            preview = "\n".join(f"- {item}" for item in errors[:6])
            if len(errors) > 6:
                preview += f"\n... and {len(errors) - 6} more"
            QMessageBox.warning(self, "Theme Load Warnings", preview)

    def _open_themes_folder(self) -> None:
        themes_dir = self._theme_service.user_themes_dir
        themes_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(themes_dir)))

    def _update_theme_details(self) -> None:
        details = self._theme_combo.currentData(Qt.ItemDataRole.ToolTipRole)
        if not isinstance(details, str):
            details = ""
        self._theme_details.setText(details)
