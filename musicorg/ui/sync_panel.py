"""Tab 4: Configure dirs, plan sync, execute copy."""

from __future__ import annotations

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from musicorg.core.syncer import SyncPlan
from musicorg.ui.widgets.dir_picker import DirPicker
from musicorg.ui.widgets.progress_bar import ProgressIndicator
from musicorg.workers.sync_worker import SyncExecuteWorker, SyncPlanWorker

STATUS_COLORS = {
    "pending": "#2196F3",
    "copied": "#4CAF50",
    "exists": "#FF9800",
    "error": "#F44336",
}


class SyncPanel(QWidget):
    """Panel for planning and executing file sync operations."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plan: SyncPlan | None = None
        self._plan_worker: SyncPlanWorker | None = None
        self._plan_thread: QThread | None = None
        self._exec_worker: SyncExecuteWorker | None = None
        self._exec_thread: QThread | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Configuration
        config_group = QGroupBox("Sync Configuration")
        config_layout = QFormLayout(config_group)

        self._source_picker = DirPicker("Browse...")
        self._dest_picker = DirPicker("Browse...")
        self._format_edit = QLineEdit("$albumartist/$album/$track $title")

        config_layout.addRow("Source Directory:", self._source_picker)
        config_layout.addRow("Destination Directory:", self._dest_picker)
        config_layout.addRow("Path Format:", self._format_edit)
        layout.addWidget(config_group)

        # Buttons
        btn_layout = QHBoxLayout()
        self._plan_btn = QPushButton("Plan Sync")
        self._plan_btn.clicked.connect(self._start_plan)
        self._sync_btn = QPushButton("Start Sync")
        self._sync_btn.setEnabled(False)
        self._sync_btn.clicked.connect(self._start_sync)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._cancel_sync)
        btn_layout.addWidget(self._plan_btn)
        btn_layout.addWidget(self._sync_btn)
        btn_layout.addWidget(self._cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Summary
        self._summary_label = QLabel("")
        layout.addWidget(self._summary_label)

        # Plan table
        self._plan_table = QTableWidget()
        self._plan_table.setColumnCount(3)
        self._plan_table.setHorizontalHeaderLabels(["Source", "Destination", "Status"])
        header = self._plan_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._plan_table.setAlternatingRowColors(True)
        layout.addWidget(self._plan_table, 1)

        # Progress
        self._progress = ProgressIndicator()
        layout.addWidget(self._progress)

    def set_source_dir(self, path: str) -> None:
        self._source_picker.set_path(path)

    def set_dest_dir(self, path: str) -> None:
        self._dest_picker.set_path(path)

    def set_path_format(self, fmt: str) -> None:
        self._format_edit.setText(fmt)

    def _start_plan(self) -> None:
        source = self._source_picker.path()
        dest = self._dest_picker.path()
        if not source:
            QMessageBox.warning(self, "Missing", "Please select a source directory.")
            return
        if not dest:
            QMessageBox.warning(self, "Missing", "Please select a destination directory.")
            return

        self._plan_btn.setEnabled(False)
        self._sync_btn.setEnabled(False)
        self._plan_table.setRowCount(0)
        self._progress.start("Planning sync...")

        path_format = self._format_edit.text().strip() or "$albumartist/$album/$track $title"

        self._plan_worker = SyncPlanWorker(source, dest, path_format)
        self._plan_thread = QThread()
        self._plan_worker.moveToThread(self._plan_thread)
        self._plan_thread.started.connect(self._plan_worker.run)
        self._plan_worker.progress.connect(
            self._on_plan_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        self._plan_worker.finished.connect(self._on_plan_done)
        self._plan_worker.error.connect(self._on_plan_error)
        self._plan_worker.finished.connect(self._plan_thread.quit)
        self._plan_worker.error.connect(self._plan_thread.quit)
        self._plan_thread.finished.connect(self._cleanup_plan)
        self._plan_thread.start()

    def _on_plan_done(self, plan: SyncPlan) -> None:
        self._plan = plan
        self._populate_plan_table()
        self._plan_btn.setEnabled(True)
        self._sync_btn.setEnabled(plan.to_copy > 0)
        summary = (
            f"Total: {plan.total} | "
            f"To copy: {plan.to_copy} | "
            f"Already exists: {plan.already_exists} | "
            f"Errors: {plan.errors}"
        )
        self._summary_label.setText(summary)
        self._progress.finish("Plan ready")

    def _on_plan_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, f"Scanning: {message}")

    def _on_plan_error(self, msg: str) -> None:
        self._plan_btn.setEnabled(True)
        self._progress.finish(f"Error: {msg}")
        QMessageBox.critical(self, "Plan Error", msg)

    def _populate_plan_table(self) -> None:
        if not self._plan:
            return
        self._plan_table.setRowCount(len(self._plan.items))
        for i, item in enumerate(self._plan.items):
            src_item = QTableWidgetItem(str(item.source))
            dest_item = QTableWidgetItem(str(item.dest))
            status_item = QTableWidgetItem(item.status.upper())

            color = STATUS_COLORS.get(item.status, "#000000")
            from PySide6.QtGui import QColor
            status_item.setForeground(QColor(color))

            self._plan_table.setItem(i, 0, src_item)
            self._plan_table.setItem(i, 1, dest_item)
            self._plan_table.setItem(i, 2, status_item)

    def _start_sync(self) -> None:
        if not self._plan:
            return

        self._plan_btn.setEnabled(False)
        self._sync_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._progress.start("Syncing files...")

        path_format = self._format_edit.text().strip() or "$albumartist/$album/$track $title"

        self._exec_worker = SyncExecuteWorker(self._plan, path_format)
        self._exec_thread = QThread()
        self._exec_worker.moveToThread(self._exec_thread)
        self._exec_thread.started.connect(self._exec_worker.run)
        self._exec_worker.progress.connect(
            self._on_sync_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        self._exec_worker.finished.connect(self._on_sync_done)
        self._exec_worker.error.connect(self._on_sync_error)
        self._exec_worker.cancelled.connect(self._on_sync_cancelled)
        self._exec_worker.finished.connect(self._exec_thread.quit)
        self._exec_worker.error.connect(self._exec_thread.quit)
        self._exec_worker.cancelled.connect(self._exec_thread.quit)
        self._exec_thread.finished.connect(self._cleanup_exec)
        self._exec_thread.start()

    def _cancel_sync(self) -> None:
        if self._exec_worker:
            self._exec_worker.cancel()

    def _on_sync_done(self, plan: SyncPlan) -> None:
        self._plan = plan
        self._populate_plan_table()
        copied = sum(1 for i in plan.items if i.status == "copied")
        errors = sum(1 for i in plan.items if i.status == "error")
        self._progress.finish(f"Sync complete: {copied} copied, {errors} errors")
        self._plan_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        summary = (
            f"Total: {plan.total} | "
            f"Copied: {copied} | "
            f"Already exists: {plan.already_exists} | "
            f"Errors: {errors}"
        )
        self._summary_label.setText(summary)

    def _on_sync_progress(self, current: int, total: int, message: str) -> None:
        self._progress.update_progress(current, total, f"Copying: {message}")

    def _on_sync_error(self, msg: str) -> None:
        self._plan_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress.finish(f"Error: {msg}")
        QMessageBox.critical(self, "Sync Error", msg)

    def _on_sync_cancelled(self) -> None:
        self._plan_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress.finish("Sync cancelled")

    def _cleanup_plan(self) -> None:
        if self._plan_worker:
            self._plan_worker.deleteLater()
            self._plan_worker = None
        if self._plan_thread:
            self._plan_thread.deleteLater()
            self._plan_thread = None

    def _cleanup_exec(self) -> None:
        if self._exec_worker:
            self._exec_worker.deleteLater()
            self._exec_worker = None
        if self._exec_thread:
            self._exec_thread.deleteLater()
            self._exec_thread = None
