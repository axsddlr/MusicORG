"""Tests for musicorg.core.scanner."""

import tempfile
from pathlib import Path

import pytest

from musicorg.core.scanner import AUDIO_EXTENSIONS, AudioFile, FileScanner


@pytest.fixture
def audio_dir(tmp_path):
    """Create a temp directory with fake audio files."""
    (tmp_path / "song1.mp3").write_bytes(b"\x00" * 100)
    (tmp_path / "song2.flac").write_bytes(b"\x00" * 200)
    (tmp_path / "readme.txt").write_bytes(b"not audio")
    (tmp_path / "image.jpg").write_bytes(b"\xff\xd8" * 50)

    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "song3.mp3").write_bytes(b"\x00" * 150)
    return tmp_path


class TestAudioFile:
    def test_audio_file_properties(self, tmp_path):
        p = tmp_path / "test.mp3"
        p.write_bytes(b"\x00" * 256)
        af = AudioFile(path=p)
        assert af.extension == ".mp3"
        assert af.size == 256
        assert af.path == p

    def test_audio_file_flac(self, tmp_path):
        p = tmp_path / "test.flac"
        p.write_bytes(b"\x00" * 512)
        af = AudioFile(path=p)
        assert af.extension == ".flac"
        assert af.size == 512


class TestFileScanner:
    def test_scan_finds_audio_files(self, audio_dir):
        scanner = FileScanner(audio_dir)
        results = scanner.scan()
        names = {af.path.name for af in results}
        assert "song1.mp3" in names
        assert "song2.flac" in names
        assert "song3.mp3" in names

    def test_scan_ignores_non_audio(self, audio_dir):
        scanner = FileScanner(audio_dir)
        results = scanner.scan()
        names = {af.path.name for af in results}
        assert "readme.txt" not in names
        assert "image.jpg" not in names

    def test_scan_count(self, audio_dir):
        scanner = FileScanner(audio_dir)
        results = scanner.scan()
        assert len(results) == 3

    def test_scan_empty_dir(self, tmp_path):
        scanner = FileScanner(tmp_path)
        results = scanner.scan()
        assert results == []

    def test_scan_iter(self, audio_dir):
        scanner = FileScanner(audio_dir)
        results = list(scanner.scan_iter())
        assert len(results) == 3

    def test_audio_extensions(self):
        assert ".mp3" in AUDIO_EXTENSIONS
        assert ".flac" in AUDIO_EXTENSIONS
        assert ".wav" not in AUDIO_EXTENSIONS
