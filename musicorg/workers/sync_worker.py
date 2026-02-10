"""Worker for executing file sync operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from musicorg.core.syncer import SyncManager
from musicorg.workers.base_worker import BaseWorker

if TYPE_CHECKING:
    from musicorg.core.syncer import SyncPlan


class SyncPlanWorker(BaseWorker):
    """Plans a sync operation in a background thread."""

    def __init__(self, source_dir: str, dest_dir: str,
                 path_format: str, include_reverse: bool = False) -> None:
        super().__init__()
        self._source_dir = source_dir
        self._dest_dir = dest_dir
        self._path_format = path_format
        self._include_reverse = include_reverse

    def run(self) -> None:
        self.started.emit()
        try:
            mgr = SyncManager(self._path_format)
            plan = mgr.plan_sync(
                self._source_dir,
                self._dest_dir,
                progress_cb=lambda cur, tot, msg: self.progress.emit(cur, tot, msg),
                include_reverse=self._include_reverse,
            )
            self.finished.emit(plan)
        except Exception as e:
            self.error.emit(str(e))


class SyncExecuteWorker(BaseWorker):
    """Executes a sync plan in a background thread."""

    def __init__(self, plan: SyncPlan, path_format: str) -> None:
        super().__init__()
        self._plan = plan
        self._path_format = path_format
        self._sync_manager: SyncManager | None = None

    def cancel(self) -> None:
        super().cancel()
        if self._sync_manager:
            self._sync_manager.cancel()

    def run(self) -> None:
        self.started.emit()
        try:
            self._sync_manager = SyncManager(self._path_format)
            result = self._sync_manager.execute_sync(
                self._plan,
                progress_cb=lambda cur, tot, msg: self.progress.emit(cur, tot, msg),
            )
            if self._is_cancelled:
                self.cancelled.emit()
            else:
                self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
