"""Tests for musicorg.workers sync and duplicate workers."""

from pathlib import Path
import tempfile

import pytest

from musicorg.core.syncer import SyncPlan, SyncItem
from musicorg.core.duplicate_finder import DuplicateGroup, DuplicateFile
from musicorg.workers.sync_worker import SyncPlanWorker, SyncExecuteWorker
from musicorg.workers.duplicate_worker import DuplicateScanWorker, DuplicateDeleteWorker


class TestSyncPlanWorker:
    """Tests for SyncPlanWorker."""

    @pytest.fixture
    def source_and_dest_dirs(self, tmp_path):
        """Create source and destination directories."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        # Create a test file
        (source / "test.mp3").write_bytes(b"\x00" * 100)
        return source, dest

    def test_sync_plan_worker_creation(self, source_and_dest_dirs):
        """Test SyncPlanWorker can be instantiated."""
        source, dest = source_and_dest_dirs
        worker = SyncPlanWorker(
            source_dir=str(source),
            dest_dir=str(dest),
            path_format="$artist/$album/$track $title"
        )
        assert worker is not None
        assert worker._is_cancelled is False

    def test_sync_plan_worker_cancel(self, source_and_dest_dirs):
        """Test cancel sets the cancelled flag."""
        source, dest = source_and_dest_dirs
        worker = SyncPlanWorker(
            source_dir=str(source),
            dest_dir=str(dest),
            path_format="$artist/$album/$track $title"
        )
        worker.cancel()
        assert worker._is_cancelled is True

    def test_sync_plan_worker_has_signals(self, source_and_dest_dirs):
        """Test SyncPlanWorker has required signals."""
        source, dest = source_and_dest_dirs
        worker = SyncPlanWorker(
            source_dir=str(source),
            dest_dir=str(dest),
            path_format="$artist/$album/$track $title"
        )
        assert hasattr(worker, 'started')
        assert hasattr(worker, 'progress')
        assert hasattr(worker, 'finished')
        assert hasattr(worker, 'error')


class TestSyncExecuteWorker:
    """Tests for SyncExecuteWorker."""

    @pytest.fixture
    def sync_plan(self, tmp_path):
        """Create a simple sync plan."""
        source = tmp_path / "source" / "test.mp3"
        source.parent.mkdir()
        source.write_bytes(b"\x00" * 100)
        dest = tmp_path / "dest" / "test.mp3"
        
        plan = SyncPlan()
        plan.items.append(SyncItem(source=source, dest=dest, status="pending"))
        return plan

    def test_sync_execute_worker_creation(self, sync_plan):
        """Test SyncExecuteWorker can be instantiated."""
        worker = SyncExecuteWorker(plan=sync_plan, path_format="$artist/$album/$track $title")
        assert worker is not None
        assert worker._is_cancelled is False

    def test_sync_execute_worker_cancel(self, sync_plan):
        """Test cancel sets the cancelled flag."""
        worker = SyncExecuteWorker(plan=sync_plan, path_format="$artist/$album/$track $title")
        worker.cancel()
        assert worker._is_cancelled is True

    def test_sync_execute_worker_has_signals(self, sync_plan):
        """Test SyncExecuteWorker has required signals."""
        worker = SyncExecuteWorker(plan=sync_plan, path_format="$artist/$album/$track $title")
        assert hasattr(worker, 'started')
        assert hasattr(worker, 'progress')
        assert hasattr(worker, 'finished')
        assert hasattr(worker, 'error')
        assert hasattr(worker, 'cancelled')


class TestDuplicateScanWorker:
    """Tests for DuplicateScanWorker."""

    @pytest.fixture
    def sample_dir(self, tmp_path):
        """Create a sample directory."""
        (tmp_path / "song1.mp3").write_bytes(b"\x00" * 100)
        (tmp_path / "song2.mp3").write_bytes(b"\x00" * 100)
        return tmp_path

    def test_duplicate_scan_worker_creation(self, sample_dir):
        """Test DuplicateScanWorker can be instantiated."""
        worker = DuplicateScanWorker(root_dir=str(sample_dir))
        assert worker is not None
        assert worker._is_cancelled is False

    def test_duplicate_scan_worker_cancel(self, sample_dir):
        """Test cancel sets the cancelled flag."""
        worker = DuplicateScanWorker(root_dir=str(sample_dir))
        worker.cancel()
        assert worker._is_cancelled is True

    def test_duplicate_scan_worker_has_signals(self, sample_dir):
        """Test DuplicateScanWorker has required signals."""
        worker = DuplicateScanWorker(root_dir=str(sample_dir))
        assert hasattr(worker, 'started')
        assert hasattr(worker, 'progress')
        assert hasattr(worker, 'finished')
        assert hasattr(worker, 'error')
        assert hasattr(worker, 'cancelled')

    def test_duplicate_scan_worker_with_cache(self, sample_dir, tmp_path):
        """Test DuplicateScanWorker with cache database path."""
        cache_path = str(tmp_path / "cache.db")
        worker = DuplicateScanWorker(
            root_dir=str(sample_dir),
            match_artist=True,
            cache_db_path=cache_path
        )
        assert worker is not None
        assert worker._match_artist is True
        assert worker._cache_db_path == cache_path


class TestDuplicateDeleteWorker:
    """Tests for DuplicateDeleteWorker."""

    @pytest.fixture
    def paths_to_delete(self, tmp_path):
        """Create paths to delete."""
        file1 = tmp_path / "file1.mp3"
        file2 = tmp_path / "file2.mp3"
        file1.write_bytes(b"\x00" * 100)
        file2.write_bytes(b"\x00" * 100)
        return [file1, file2]

    def test_duplicate_delete_worker_creation(self, paths_to_delete):
        """Test DuplicateDeleteWorker can be instantiated."""
        worker = DuplicateDeleteWorker(paths_to_delete=paths_to_delete)
        assert worker is not None
        assert worker._is_cancelled is False

    def test_duplicate_delete_worker_cancel(self, paths_to_delete):
        """Test cancel sets the cancelled flag."""
        worker = DuplicateDeleteWorker(paths_to_delete=paths_to_delete)
        worker.cancel()
        assert worker._is_cancelled is True

    def test_duplicate_delete_worker_has_signals(self, paths_to_delete):
        """Test DuplicateDeleteWorker has required signals."""
        worker = DuplicateDeleteWorker(paths_to_delete=paths_to_delete)
        assert hasattr(worker, 'started')
        assert hasattr(worker, 'progress')
        assert hasattr(worker, 'finished')
        assert hasattr(worker, 'error')
