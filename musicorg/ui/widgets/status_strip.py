"""Bottom status strip widget inspired by MusicBee."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QWidget,
)

from musicorg import __version__


class StatusStrip(QFrame):
    """Compact bottom status bar with message, progress, and info labels."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusStrip")
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)

        self._message_label = QLabel("Ready")
        self._message_label.setObjectName("StatusMessage")
        layout.addWidget(self._message_label)

        layout.addStretch(1)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedWidth(160)
        self._progress_bar.setFixedHeight(14)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)

        self._file_count_label = QLabel("")
        self._file_count_label.setObjectName("StatusDetail")
        layout.addWidget(self._file_count_label)

        self._version_label = QLabel(f"v{__version__}")
        self._version_label.setObjectName("StatusMuted")
        layout.addWidget(self._version_label)

        self._clear_timer = QTimer(self)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.timeout.connect(lambda: self._message_label.setText("Ready"))

    def show_message(self, text: str, timeout_ms: int = 0) -> None:
        self._message_label.setText(text)
        if timeout_ms > 0:
            self._clear_timer.start(timeout_ms)

    def show_progress(self, current: int, total: int) -> None:
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._progress_bar.show()

    def hide_progress(self) -> None:
        self._progress_bar.hide()

    def set_file_count(self, total: int, selected: int = 0) -> None:
        if selected:
            self._file_count_label.setText(f"{selected}/{total} files")
        elif total:
            self._file_count_label.setText(f"{total} files")
        else:
            self._file_count_label.setText("")
