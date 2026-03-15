"""Tests for batch file rename planning and execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from musicorg.core.batch_rename import (
    BatchRenameRule,
    apply_batch_rename_to_tags,
    build_batch_rename_preview,
)
from musicorg.core.tagger import TagData
from musicorg.workers.file_rename_worker import FileRenameWorker


class TestBatchRenamePreview:
    def test_plain_text_suffix_removal(self, tmp_path: Path):
        first = tmp_path / "Daily Mix 1 - SpotubeDL.com.mp3"
        second = tmp_path / "AGAIN - SAHXL - SpotubeDL.com.mp3"
        first.write_bytes(b"1")
        second.write_bytes(b"2")

        preview = build_batch_rename_preview(
            [first, second],
            BatchRenameRule(pattern=" - SpotubeDL.com"),
        )

        assert preview.total_count == 2
        assert preview.unchanged_count == 0
        assert [item.destination.name for item in preview.items] == [
            "Daily Mix 1.mp3",
            "AGAIN - SAHXL.mp3",
        ]
        assert len(preview.planned_items) == 2

    def test_regex_suffix_removal(self, tmp_path: Path):
        source = tmp_path / "track - SpotubeDL.com.mp3"
        source.write_bytes(b"1")

        preview = build_batch_rename_preview(
            [source],
            BatchRenameRule(
                pattern=r"\s+-\s+SpotubeDL\.com$",
                replacement="",
                use_regex=True,
            ),
        )

        assert len(preview.items) == 1
        assert preview.items[0].destination.name == "track.mp3"

    def test_trims_space_before_extension_after_replacement(self, tmp_path: Path):
        source = tmp_path / "AGAIN - SAHXL - SpotubeDL.com .mp3"
        source.write_bytes(b"1")

        preview = build_batch_rename_preview(
            [source],
            BatchRenameRule(pattern=" - SpotubeDL.com"),
        )

        assert len(preview.items) == 1
        assert preview.items[0].destination.name == "AGAIN - SAHXL.mp3"

    def test_detects_duplicate_destinations(self, tmp_path: Path):
        first = tmp_path / "track-1.mp3"
        second = tmp_path / "track-2.mp3"
        first.write_bytes(b"1")
        second.write_bytes(b"2")

        with pytest.raises(ValueError, match="duplicate filenames"):
            build_batch_rename_preview(
                [first, second],
                BatchRenameRule(
                    pattern=r"-\d$",
                    replacement="",
                    use_regex=True,
                ),
            )

    def test_detects_existing_destination_conflicts(self, tmp_path: Path):
        source = tmp_path / "track - SpotubeDL.com.mp3"
        conflict = tmp_path / "track.mp3"
        source.write_bytes(b"1")
        conflict.write_bytes(b"2")

        with pytest.raises(ValueError, match="Destination already exists"):
            build_batch_rename_preview(
                [source],
                BatchRenameRule(pattern=" - SpotubeDL.com"),
            )

    def test_rejects_invalid_regex(self, tmp_path: Path):
        source = tmp_path / "track.mp3"
        source.write_bytes(b"1")

        with pytest.raises(ValueError, match="Invalid regex"):
            build_batch_rename_preview(
                [source],
                BatchRenameRule(pattern="(", use_regex=True),
            )


class TestMetadataReplacement:
    def test_apply_to_selected_metadata_fields(self):
        tags = TagData(
            title="Track - SpotubeDL.com",
            artist="Artist - SpotubeDL.com",
            album="Album - SpotubeDL.com",
            albumartist="Album Artist - SpotubeDL.com",
        )

        updated, changed = apply_batch_rename_to_tags(
            tags,
            BatchRenameRule(pattern=" - SpotubeDL.com"),
            ("title", "artist"),
        )

        assert changed is True
        assert updated.title == "Track"
        assert updated.artist == "Artist"
        assert updated.album == "Album - SpotubeDL.com"
        assert updated.albumartist == "Album Artist - SpotubeDL.com"


class TestFileRenameWorker:
    def test_worker_renames_files(self, tmp_path: Path):
        source = tmp_path / "track - SpotubeDL.com.mp3"
        destination = tmp_path / "track.mp3"
        source.write_bytes(b"data")

        finished_payloads: list[object] = []
        errors: list[str] = []
        worker = FileRenameWorker([(source, destination)])
        worker.finished.connect(finished_payloads.append)
        worker.error.connect(errors.append)

        worker.run()

        assert not errors
        assert finished_payloads == [{
            "renamed": 1,
            "total": 1,
            "metadata_updated": 0,
            "metadata_failed": [],
        }]
        assert not source.exists()
        assert destination.read_bytes() == b"data"

    def test_worker_handles_internal_destination_occupancy(self, tmp_path: Path):
        first = tmp_path / "a.mp3"
        second = tmp_path / "b.mp3"
        third = tmp_path / "c.mp3"
        first.write_bytes(b"a")
        second.write_bytes(b"b")

        finished_payloads: list[object] = []
        errors: list[str] = []
        worker = FileRenameWorker([(first, second), (second, third)])
        worker.finished.connect(finished_payloads.append)
        worker.error.connect(errors.append)

        worker.run()

        assert not errors
        assert finished_payloads == [{
            "renamed": 2,
            "total": 2,
            "metadata_updated": 0,
            "metadata_failed": [],
        }]
        assert second.read_bytes() == b"a"
        assert third.read_bytes() == b"b"

    def test_worker_can_update_metadata_after_rename(self, tmp_path: Path, monkeypatch):
        source = tmp_path / "track - SpotubeDL.com.mp3"
        destination = tmp_path / "track.mp3"
        source.write_bytes(b"data")
        writes: dict[str, TagData] = {}

        class FakeTagManager:
            def read(self, path):
                return TagData(
                    title="Track - SpotubeDL.com",
                    artist="Artist - SpotubeDL.com",
                    album="Album",
                    albumartist="Album Artist - SpotubeDL.com",
                )

            def write(self, path, tags):
                writes[str(path)] = tags

        monkeypatch.setattr("musicorg.workers.file_rename_worker.TagManager", FakeTagManager)

        finished_payloads: list[object] = []
        errors: list[str] = []
        worker = FileRenameWorker(
            [(source, destination)],
            metadata_rule=BatchRenameRule(pattern=" - SpotubeDL.com"),
            metadata_fields=("title", "artist", "albumartist"),
        )
        worker.finished.connect(finished_payloads.append)
        worker.error.connect(errors.append)

        worker.run()

        assert not errors
        assert finished_payloads == [{
            "renamed": 1,
            "total": 1,
            "metadata_updated": 1,
            "metadata_failed": [],
        }]
        assert writes[str(destination)].title == "Track"
        assert writes[str(destination)].artist == "Artist"
        assert writes[str(destination)].album == "Album"
        assert writes[str(destination)].albumartist == "Album Artist"

    def test_worker_cancelled_before_start(self, tmp_path: Path):
        source = tmp_path / "track.mp3"
        destination = tmp_path / "renamed.mp3"
        source.write_bytes(b"data")

        cancelled = []
        finished_payloads: list[object] = []
        worker = FileRenameWorker([(source, destination)])
        worker.cancelled.connect(lambda: cancelled.append(True))
        worker.finished.connect(finished_payloads.append)
        worker.cancel()

        worker.run()

        assert cancelled == [True]
        assert finished_payloads == []
        assert source.exists()
        assert not destination.exists()
