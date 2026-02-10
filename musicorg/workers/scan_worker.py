"""Worker for scanning directories for audio files."""

from __future__ import annotations

from time import monotonic

from musicorg.core.scanner import FileScanner
from musicorg.workers.base_worker import BaseWorker


class ScanWorker(BaseWorker):
    """Scans a directory for audio files in a background thread."""

    def __init__(self, root_dir: str) -> None:
        super().__init__()
        self._root_dir = root_dir

    def run(self) -> None:
        self.started.emit()
        try:
            scanner = FileScanner(self._root_dir)
            results = []
            last_emit = 0.0
            for af in scanner.scan_iter():
                if self._is_cancelled:
                    self.cancelled.emit()
                    return
                results.append(af)
                count = len(results)
                now = monotonic()

                # Throttle progress events to avoid flooding the UI event queue.
                if count == 1 or count % 25 == 0 or (now - last_emit) >= 0.05:
                    self.progress.emit(count, 0, af.path.name)
                    last_emit = now

            if results:
                self.progress.emit(len(results), 0, results[-1].path.name)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))
