"""Tests for musicorg.core.syncer."""

from pathlib import Path

import pytest

from musicorg.core.syncer import (
    SyncItem, SyncManager, SyncPlan,
    _build_dest_path, _sanitize_filename,
)
from musicorg.core.tagger import TagData


class TestSanitizeFilename:
    def test_removes_illegal_chars(self):
        assert _sanitize_filename('a<b>c:d"e') == "a_b_c_d_e"

    def test_removes_question_mark(self):
        assert _sanitize_filename("what?") == "what_"

    def test_strips_dots_and_spaces(self):
        assert _sanitize_filename("  ..name.. ") == "name"

    def test_empty_returns_underscore(self):
        assert _sanitize_filename("") == "_"

    def test_normal_name_unchanged(self):
        assert _sanitize_filename("My Song") == "My Song"


class TestBuildDestPath:
    def test_basic_format(self):
        tags = {"albumartist": "Artist", "album": "Album", "track": 3, "title": "Song"}
        result = _build_dest_path(
            Path("/dest"), tags, ".mp3",
            "$albumartist/$album/$track $title"
        )
        assert result == Path("/dest/Artist/Album/03 Song.mp3")

    def test_missing_tags_use_fallbacks(self):
        result = _build_dest_path(
            Path("/dest"), {}, ".flac",
            "$albumartist/$album/$track $title"
        )
        assert "Unknown Artist" in str(result)
        assert "Unknown Album" in str(result)
        assert "Unknown Title" in str(result)

    def test_artist_fallback(self):
        tags = {"artist": "Solo", "album": "LP", "track": 1, "title": "Song"}
        result = _build_dest_path(
            Path("/dest"), tags, ".mp3",
            "$albumartist/$album/$track $title"
        )
        assert "Solo" in str(result)

    def test_sanitizes_illegal_chars(self):
        tags = {"albumartist": "AC/DC", "album": "Back: In", "track": 1, "title": "TNT"}
        result = _build_dest_path(
            Path("/dest"), tags, ".mp3",
            "$albumartist/$album/$track $title"
        )
        assert ":" not in result.name
        # The forward slash in AC/DC is handled by path splitting


class TestSyncPlan:
    def test_counts(self):
        plan = SyncPlan(items=[
            SyncItem(source=Path("a"), dest=Path("b"), status="pending"),
            SyncItem(source=Path("c"), dest=Path("d"), status="exists"),
            SyncItem(source=Path("e"), dest=Path("f"), status="pending"),
            SyncItem(source=Path("g"), dest=Path("h"), status="error"),
        ])
        assert plan.total == 4
        assert plan.to_copy == 2
        assert plan.already_exists == 1
        assert plan.errors == 1


class TestSyncManager:
    def test_plan_sync_empty_source(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()

        mgr = SyncManager()
        plan = mgr.plan_sync(source, dest)
        assert plan.total == 0

    def test_execute_sync_creates_files(self, tmp_path):
        source = tmp_path / "src"
        dest = tmp_path / "dst"
        source.mkdir()
        dest.mkdir()

        # Create a pending item
        src_file = source / "test.txt"
        src_file.write_text("hello")
        dest_file = dest / "out" / "test.txt"

        plan = SyncPlan(items=[
            SyncItem(source=src_file, dest=dest_file, status="pending"),
        ])

        mgr = SyncManager()
        result = mgr.execute_sync(plan)
        assert dest_file.exists()
        assert result.items[0].status == "copied"

    def test_execute_sync_skips_exists(self, tmp_path):
        plan = SyncPlan(items=[
            SyncItem(source=Path("a"), dest=Path("b"), status="exists"),
        ])
        mgr = SyncManager()
        result = mgr.execute_sync(plan)
        assert result.items[0].status == "exists"

    def test_cancel(self):
        mgr = SyncManager()
        mgr.cancel()
        assert mgr._cancelled is True

    def test_plan_sync_with_reverse_by_track(self, tmp_path):
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        src_song1 = source / "song1.mp3"
        src_song1.write_bytes(b"src")
        dst_song1 = dest / "song1.mp3"
        dst_song1.write_bytes(b"dst1")
        dst_song2 = dest / "song2.mp3"
        dst_song2.write_bytes(b"dst2")

        mgr = SyncManager()

        def fake_read(path: Path) -> TagData:
            stem = path.stem.lower()
            track_num = 1 if stem == "song1" else 2
            return TagData(
                title=stem,
                artist="Artist",
                album="Album",
                track=track_num,
            )

        mgr._tag_manager.read = fake_read  # type: ignore[method-assign]

        plan = mgr.plan_sync(source, dest, include_reverse=True)
        reverse_items = [i for i in plan.items if i.source.parent == dest and i.dest.parent != dest]

        # song2 exists only in destination, so it should be planned back into source.
        assert any(i.source == dst_song2 for i in reverse_items)
        # song1 exists in both trees (same track identity), so no reverse copy for it.
        assert not any(i.source == dst_song1 for i in reverse_items)
