"""Base worker class with standard signals for background operations."""

from __future__ import annotations

from threading import Event

from PySide6.QtCore import QObject, Signal


class BaseWorker(QObject):
    """Base class for background workers using moveToThread pattern.

    Usage:
        worker = SomeWorker(args)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()
    """

    started = Signal()
    progress = Signal(int, int, str)    # current, total, message
    finished = Signal(object)           # result data
    error = Signal(str)                 # error message
    cancelled = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cancel_event = Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    @property
    def _is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def run(self) -> None:
        """Override in subclass. Called when thread starts."""
        raise NotImplementedError
