"""Shared fixtures for musicorg tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from musicorg.core.tagger import TagData


@pytest.fixture
def tmp_audio_file(tmp_path: Path) -> Path:
    """Create a minimal audio-like file for tag operations."""
    path = tmp_path / "song.mp3"
    path.write_bytes(b"audio data")
    return path


@pytest.fixture
def tmp_library(tmp_path: Path) -> dict[str, Path]:
    """Create a small library tree with audio files."""
    paths: dict[str, Path] = {}
    for name in ("song1.mp3", "song2.flac", "song3.m4a"):
        path = tmp_path / name
        path.write_bytes(b"audio")
        paths[name] = path
    for sub, names in (
        ("Artist", ("track1.mp3", "track2.ogg")),
        ("Artist/Album", ("01 intro.flac", "02 main.mp3")),
    ):
        for name in names:
            path = tmp_path / sub / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"audio")
            paths[f"{sub}/{name}"] = path
    return paths


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database path."""
    return tmp_path / "test.db"


@pytest.fixture
def sample_tags() -> TagData:
    """Standard sample tags for tests."""
    return TagData(
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        albumartist="Test Album Artist",
        track=1,
        disc=1,
        year=2024,
        genre="Test",
        duration=180.0,
    )
