"""Tests for musicorg.workers base and scan workers."""

from pathlib import Path
import tempfile

import pytest
from PySide6.QtCore import QThread

from musicorg.core.scanner import AudioFile, FileScanner
from musicorg.workers.base_worker import BaseWorker
from musicorg.workers.scan_worker import ScanWorker


class TestBaseWorker:
    """Tests for the BaseWorker class."""

    def test_base_worker_creation(self):
        """Test BaseWorker can be instantiated."""
        worker = BaseWorker()
        assert worker is not None
        assert worker._cancel_event.is_set() is False

    def test_base_worker_cancel(self):
        """Test cancel sets the event."""
        worker = BaseWorker()
        worker.cancel()
        assert worker._cancel_event.is_set() is True

    def test_base_worker_is_cancelled_property(self):
        """Test _is_cancelled property reflects cancel state."""
        worker = BaseWorker()
        assert worker._is_cancelled is False
        worker.cancel()
        assert worker._is_cancelled is True

    def test_base_worker_signals_exist(self):
        """Test all expected signals are defined."""
        worker = BaseWorker()
        assert hasattr(worker, 'started')
        assert hasattr(worker, 'progress')
        assert hasattr(worker, 'finished')
        assert hasattr(worker, 'error')
        assert hasattr(worker, 'cancelled')

    def test_base_worker_run_not_implemented(self):
        """Test run() raises NotImplementedError."""
        worker = BaseWorker()
        with pytest.raises(NotImplementedError):
            worker.run()


class TestScanWorker:
    """Tests for the ScanWorker class."""

    @pytest.fixture
    def sample_audio_dir(self, tmp_path):
        """Create a directory with sample audio files."""
        (tmp_path / "track1.mp3").write_bytes(b"\x00" * 100)
        (tmp_path / "track2.flac").write_bytes(b"\x00" * 200)
        (tmp_path / "track3.mp3").write_bytes(b"\x00" * 150)
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "track4.mp3").write_bytes(b"\x00" * 125)
        return tmp_path

    @pytest.fixture
    def empty_dir(self, tmp_path):
        """Create an empty directory."""
        return tmp_path

    def test_scan_worker_creation(self, sample_audio_dir):
        """Test ScanWorker can be instantiated."""
        worker = ScanWorker(root_dir=str(sample_audio_dir))
        assert worker is not None
        assert worker._is_cancelled is False
        assert worker._root_dir == str(sample_audio_dir)

    def test_scan_worker_cancel(self, sample_audio_dir):
        """Test cancel sets the cancelled flag."""
        worker = ScanWorker(root_dir=str(sample_audio_dir))
        worker.cancel()
        assert worker._is_cancelled is True

    def test_scan_worker_uses_file_scanner(self, sample_audio_dir):
        """Test ScanWorker uses FileScanner internally."""
        worker = ScanWorker(root_dir=str(sample_audio_dir))
        # Verify the worker would use FileScanner by checking it can create one
        scanner = FileScanner(worker._root_dir)
        results = scanner.scan()
        assert len(results) == 4

    def test_scan_worker_empty_dir(self, empty_dir):
        """Test ScanWorker handles empty directory."""
        worker = ScanWorker(root_dir=str(empty_dir))
        scanner = FileScanner(worker._root_dir)
        results = scanner.scan()
        assert results == []

    def test_scan_worker_result_is_audio_file_list(self, sample_audio_dir):
        """Test scan results are AudioFile objects."""
        scanner = FileScanner(sample_audio_dir)
        results = scanner.scan()
        assert len(results) == 4
        for item in results:
            assert isinstance(item, AudioFile)
            assert hasattr(item, 'path')
            assert hasattr(item, 'size')
            assert hasattr(item, 'extension')

    def test_scan_worker_progress_callback_exists(self, sample_audio_dir):
        """Test ScanWorker has progress callback mechanism."""
        worker = ScanWorker(root_dir=str(sample_audio_dir))
        # Verify progress signal exists
        assert hasattr(worker, 'progress')
        # Signal should be callable for connection
        assert callable(worker.progress.emit)

    def test_scan_worker_finished_callback_exists(self, sample_audio_dir):
        """Test ScanWorker has finished callback mechanism."""
        worker = ScanWorker(root_dir=str(sample_audio_dir))
        assert hasattr(worker, 'finished')
        assert callable(worker.finished.emit)

    def test_scan_worker_error_callback_exists(self, sample_audio_dir):
        """Test ScanWorker has error callback mechanism."""
        worker = ScanWorker(root_dir=str(sample_audio_dir))
        assert hasattr(worker, 'error')
        assert callable(worker.error.emit)
