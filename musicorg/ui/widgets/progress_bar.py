"""Progress indicator widget."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget


class ProgressIndicator(QWidget):
    """A progress bar with status label."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._bar = QProgressBar()
        self._bar.setMinimum(0)
        self._bar.setMaximum(100)
        self._bar.setValue(0)

        self._label = QLabel()

        layout.addWidget(self._bar, 1)
        layout.addWidget(self._label)

        self.hide()

    def start(self, message: str = "Working...") -> None:
        self._set_message(message)
        self._set_range(0, 100)
        self._set_value(0)
        self.show()

    def update_progress(self, current: int, total: int, message: str = "") -> None:
        if total > 0:
            self._set_range(0, total)
            self._set_value(current)
        else:
            # Indeterminate
            self._set_range(0, 0)
        if message:
            self._set_message(message)

    def finish(self, message: str = "Done") -> None:
        self._set_range(0, 100)
        self._set_value(100)
        self._set_message(message)

    def reset(self) -> None:
        self._set_range(0, 100)
        self._set_value(0)
        self._label.clear()
        self.hide()

    def _set_range(self, minimum: int, maximum: int) -> None:
        if self._bar.minimum() != minimum or self._bar.maximum() != maximum:
            self._bar.setRange(minimum, maximum)

    def _set_value(self, value: int) -> None:
        if self._bar.value() != value:
            self._bar.setValue(value)

    def _set_message(self, message: str) -> None:
        if self._label.text() != message:
            self._label.setText(message)
