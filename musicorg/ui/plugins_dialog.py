"""Plugin manager dialog."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)


class PluginManagerDialog(QDialog):
    """Manage installed plugin enablement and diagnostics."""

    def __init__(
        self,
        runtime,
        settings,
        on_reload_requested: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._runtime = runtime
        self._settings = settings
        self._on_reload_requested = on_reload_requested
        self._updating_table = False
        self.setWindowTitle("Plugins")
        self.setMinimumSize(860, 520)
        self._setup_ui()
        self._populate()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        helper = QLabel(
            "Install plugins in the plugins folder, then enable them below. "
            "Safe mode disables third-party plugins at startup."
        )
        helper.setWordWrap(True)
        helper.setObjectName("StatusMuted")
        layout.addWidget(helper)

        self._safe_mode_checkbox = QCheckBox("Safe mode (skip non built-in plugins)")
        self._safe_mode_checkbox.toggled.connect(self._on_safe_mode_toggled)
        layout.addWidget(self._safe_mode_checkbox)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Enabled", "Name", "Version", "Author", "State", "Plugin ID"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.itemChanged.connect(self._on_table_item_changed)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, 2)

        errors_label = QLabel("Diagnostics")
        errors_label.setObjectName("SectionHeader")
        layout.addWidget(errors_label)
        self._errors = QTextEdit()
        self._errors.setReadOnly(True)
        self._errors.setMinimumHeight(130)
        layout.addWidget(self._errors, 1)

        buttons = QHBoxLayout()
        self._open_folder_btn = QPushButton("Open Plugins Folder")
        self._open_folder_btn.clicked.connect(self._open_plugins_folder)
        self._reload_btn = QPushButton("Reload Plugins")
        self._reload_btn.setProperty("role", "accent")
        self._reload_btn.clicked.connect(self._reload_plugins)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(self._open_folder_btn)
        buttons.addWidget(self._reload_btn)
        buttons.addStretch()
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    def _populate(self) -> None:
        summaries = self._runtime.available_plugins()
        self._updating_table = True
        self._table.setRowCount(len(summaries))
        for row, summary in enumerate(summaries):
            enabled_item = QTableWidgetItem("")
            enabled_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            enabled_item.setCheckState(
                Qt.CheckState.Checked if summary.enabled else Qt.CheckState.Unchecked
            )
            enabled_item.setData(Qt.ItemDataRole.UserRole, summary.plugin_id)
            self._table.setItem(row, 0, enabled_item)

            name = summary.name if not summary.is_builtin else f"{summary.name} (built-in)"
            self._table.setItem(row, 1, QTableWidgetItem(name))
            self._table.setItem(row, 2, QTableWidgetItem(summary.version))
            self._table.setItem(row, 3, QTableWidgetItem(summary.author))
            self._table.setItem(row, 4, QTableWidgetItem(summary.state.value))
            self._table.setItem(row, 5, QTableWidgetItem(summary.plugin_id))
        self._updating_table = False

        self._safe_mode_checkbox.setChecked(self._settings.plugins_safe_mode)
        errors = self._runtime.load_errors()
        if errors:
            self._errors.setPlainText("\n".join(errors))
        else:
            self._errors.setPlainText("No plugin diagnostics.")

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_table:
            return
        if item.column() != 0:
            return
        plugin_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not plugin_id:
            return
        enabled = item.checkState() == Qt.CheckState.Checked
        self._runtime.set_enabled(plugin_id, enabled)
        self._reload_plugins()

    def _on_safe_mode_toggled(self, checked: bool) -> None:
        self._settings.plugins_safe_mode = bool(checked)
        self._reload_plugins()

    def _reload_plugins(self) -> None:
        self._on_reload_requested()
        self._populate()

    def _open_plugins_folder(self) -> None:
        folder = self._runtime.user_plugins_dir
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
