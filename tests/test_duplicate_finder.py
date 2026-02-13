"""Tests for duplicate_finder core logic."""

from __future__ import annotations

from pathlib import Path

from musicorg.core.duplicate_finder import (
    DuplicateGroup,
    find_duplicates,
    normalize_title,
)
from musicorg.core.tagger import TagData


def _tag(title: str = "", artist: str = "", album: str = "", bitrate: int = 0) -> TagData:
    return TagData(title=title, artist=artist, album=album, bitrate=bitrate)


class TestNormalizeTitle:
    def test_lowercase_and_strip(self):
        assert normalize_title("  Hello World  ") == "hello world"

    def test_collapse_whitespace(self):
        assert normalize_title("a   b\t c") == "a b c"

    def test_empty(self):
        assert normalize_title("") == ""


class TestFindDuplicates:
    def test_no_duplicates_returns_empty(self):
        files = [
            (Path("a.mp3"), _tag("Song A"), 1000),
            (Path("b.flac"), _tag("Song B"), 2000),
        ]
        assert find_duplicates(files) == []

    def test_flac_wins_over_mp3(self):
        files = [
            (Path("song.mp3"), _tag("My Song"), 1000),
            (Path("song.flac"), _tag("My Song"), 2000),
        ]
        groups = find_duplicates(files)
        assert len(groups) == 1
        group = groups[0]
        assert group.kept_file is not None
        assert group.kept_file.extension == ".flac"
        assert len(group.deletable_files) == 1
        assert group.deletable_files[0].extension == ".mp3"

    def test_title_normalization(self):
        files = [
            (Path("a.mp3"), _tag("  my SONG  "), 1000),
            (Path("b.flac"), _tag("My   Song"), 2000),
        ]
        groups = find_duplicates(files)
        assert len(groups) == 1

    def test_empty_title_skipped(self):
        files = [
            (Path("a.mp3"), _tag(""), 1000),
            (Path("b.mp3"), _tag(""), 2000),
        ]
        assert find_duplicates(files) == []

    def test_different_albums_not_grouped(self):
        files = [
            (Path("a.mp3"), _tag("Song", album="Album A"), 1000),
            (Path("b.flac"), _tag("Song", album="Album B"), 2000),
        ]
        assert find_duplicates(files) == []

    def test_same_album_grouped(self):
        files = [
            (Path("a.mp3"), _tag("Song", album="Album A"), 1000),
            (Path("b.flac"), _tag("Song", album="Album A"), 2000),
        ]
        assert len(find_duplicates(files)) == 1

    def test_match_artist_prevents_cross_artist_grouping(self):
        files = [
            (Path("a.mp3"), _tag("Song", "Artist A", "Same Album"), 1000),
            (Path("b.flac"), _tag("Song", "Artist B", "Same Album"), 2000),
        ]
        # Without match_artist they group together (same title + album)
        assert len(find_duplicates(files, match_artist=False)) == 1
        # With match_artist they stay separate
        assert len(find_duplicates(files, match_artist=True)) == 0

    def test_same_format_larger_file_kept(self):
        files = [
            (Path("small.mp3"), _tag("Song"), 1000),
            (Path("big.mp3"), _tag("Song"), 5000),
        ]
        groups = find_duplicates(files)
        assert len(groups) == 1
        assert groups[0].kept_file is not None
        assert groups[0].kept_file.size == 5000

    def test_higher_bitrate_mp3_kept_over_lower(self):
        files = [
            (Path("low.mp3"), _tag("Song", bitrate=128000), 2000),
            (Path("high.mp3"), _tag("Song", bitrate=320000), 5000),
        ]
        groups = find_duplicates(files)
        assert len(groups) == 1
        kept = groups[0].kept_file
        assert kept is not None
        assert kept.bitrate == 320000
        assert kept.path == Path("high.mp3")

    def test_bitrate_wins_over_size_for_same_format(self):
        # Higher bitrate should win even if the file is smaller
        files = [
            (Path("big_low.mp3"), _tag("Song", bitrate=128000), 9000),
            (Path("small_high.mp3"), _tag("Song", bitrate=320000), 4000),
        ]
        groups = find_duplicates(files)
        assert len(groups) == 1
        kept = groups[0].kept_file
        assert kept is not None
        assert kept.bitrate == 320000
        assert kept.path == Path("small_high.mp3")

    def test_flac_still_wins_over_high_bitrate_mp3(self):
        files = [
            (Path("high.mp3"), _tag("Song", bitrate=320000), 8000),
            (Path("song.flac"), _tag("Song", bitrate=1000000), 20000),
        ]
        groups = find_duplicates(files)
        assert len(groups) == 1
        assert groups[0].kept_file.extension == ".flac"

    def test_three_way_mp3_bitrate_sort(self):
        files = [
            (Path("low.mp3"), _tag("Song", bitrate=128000), 2000),
            (Path("mid.mp3"), _tag("Song", bitrate=192000), 3000),
            (Path("high.mp3"), _tag("Song", bitrate=320000), 5000),
        ]
        groups = find_duplicates(files)
        assert len(groups) == 1
        kept = groups[0].kept_file
        assert kept is not None
        assert kept.bitrate == 320000
        deletable = groups[0].deletable_files
        assert len(deletable) == 2

    def test_three_way_duplicates(self):
        files = [
            (Path("a.mp3"), _tag("Song"), 1000),
            (Path("b.flac"), _tag("Song"), 3000),
            (Path("c.mp3"), _tag("Song"), 2000),
        ]
        groups = find_duplicates(files)
        assert len(groups) == 1
        group = groups[0]
        assert group.kept_file is not None
        assert group.kept_file.extension == ".flac"
        assert len(group.deletable_files) == 2

    def test_multiple_groups(self):
        files = [
            (Path("a1.mp3"), _tag("Alpha", album="Disc"), 1000),
            (Path("a2.flac"), _tag("Alpha", album="Disc"), 2000),
            (Path("b1.mp3"), _tag("Beta", album="Disc"), 1000),
            (Path("b2.flac"), _tag("Beta", album="Disc"), 3000),
        ]
        groups = find_duplicates(files)
        assert len(groups) == 2
