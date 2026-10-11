"""Tests for template-based file rename planning."""

from __future__ import annotations

from pathlib import Path

import pytest

from musicorg.core import template_rename
from musicorg.core.tagger import TagData
from musicorg.core.template_rename import build_template_rename


@pytest.fixture
def fake_tags(monkeypatch: pytest.MonkeyPatch) -> dict[str, TagData]:
    """Map of filename -> TagData served by a stubbed TagManager."""
    tags_by_name: dict[str, TagData] = {}

    class _FakeTagManager:
        def read(self, path: str | Path) -> TagData:
            return tags_by_name[Path(path).name]

    monkeypatch.setattr(template_rename, "TagManager", _FakeTagManager)
    return tags_by_name


def test_keeps_source_extension(tmp_path: Path, fake_tags: dict[str, TagData]) -> None:
    fake_tags["a.mp3"] = TagData(title="Song", track=1)
    items = build_template_rename([tmp_path / "a.mp3"], "$track $title")
    assert [i.new_name for i in items] == ["01 Song.mp3"]
    assert items[0].destination == tmp_path / "01 Song.mp3"


def test_does_not_double_extension_when_template_includes_it(
    tmp_path: Path, fake_tags: dict[str, TagData]
) -> None:
    fake_tags["a.FLAC"] = TagData(title="Song")
    items = build_template_rename([tmp_path / "a.FLAC"], "$title.flac")
    assert [i.new_name for i in items] == ["Song.flac"]


def test_albumartist_is_not_clobbered_by_album(
    tmp_path: Path, fake_tags: dict[str, TagData]
) -> None:
    fake_tags["a.flac"] = TagData(title="Song", album="Hits", albumartist="VA")
    items = build_template_rename([tmp_path / "a.flac"], "$albumartist - $album - $title")
    assert [i.new_name for i in items] == ["VA - Hits - Song.flac"]


def test_unknown_variable_raises(tmp_path: Path, fake_tags: dict[str, TagData]) -> None:
    fake_tags["a.mp3"] = TagData(title="Song")
    with pytest.raises(ValueError, match="bpm"):
        build_template_rename([tmp_path / "a.mp3"], "$bpm $title")


def test_empty_template_raises(tmp_path: Path, fake_tags: dict[str, TagData]) -> None:
    with pytest.raises(ValueError):
        build_template_rename([tmp_path / "a.mp3"], "   ")


def test_illegal_characters_in_tags_are_replaced(
    tmp_path: Path, fake_tags: dict[str, TagData]
) -> None:
    fake_tags["a.mp3"] = TagData(artist="AC/DC", title='Live: "Wembley"?')
    items = build_template_rename([tmp_path / "a.mp3"], "$artist - $title")
    assert len(items) == 1
    name = items[0].new_name
    assert name.endswith(".mp3")
    assert not set('<>:"/\\|?*') & set(name)
    assert items[0].destination.parent == tmp_path


def test_backslash_and_group_refs_in_tags_are_literal(
    tmp_path: Path, fake_tags: dict[str, TagData]
) -> None:
    fake_tags["a.mp3"] = TagData(title=r"Track \1 \g<0>")
    items = build_template_rename([tmp_path / "a.mp3"], "$title")
    assert len(items) == 1
    assert items[0].new_name.endswith(".mp3")


def test_unchanged_files_are_omitted(tmp_path: Path, fake_tags: dict[str, TagData]) -> None:
    fake_tags["01 Song.mp3"] = TagData(title="Song", track=1)
    assert build_template_rename([tmp_path / "01 Song.mp3"], "$track $title") == []


def test_duplicate_destinations_raise(tmp_path: Path, fake_tags: dict[str, TagData]) -> None:
    fake_tags["a.mp3"] = TagData(title="Song")
    fake_tags["b.mp3"] = TagData(title="Song")
    with pytest.raises(ValueError, match="duplicate"):
        build_template_rename([tmp_path / "a.mp3", tmp_path / "b.mp3"], "$title")


def test_same_name_in_different_folders_is_allowed(
    tmp_path: Path, fake_tags: dict[str, TagData]
) -> None:
    fake_tags["a.mp3"] = TagData(title="Song")
    items = build_template_rename(
        [tmp_path / "x" / "a.mp3", tmp_path / "y" / "a.mp3"], "$title"
    )
    assert [i.destination for i in items] == [
        tmp_path / "x" / "Song.mp3",
        tmp_path / "y" / "Song.mp3",
    ]


def test_existing_destination_on_disk_raises(
    tmp_path: Path, fake_tags: dict[str, TagData]
) -> None:
    (tmp_path / "a.mp3").write_bytes(b"a")
    (tmp_path / "Song.mp3").write_bytes(b"other")
    fake_tags["a.mp3"] = TagData(title="Song")
    with pytest.raises(ValueError, match="already exists"):
        build_template_rename([tmp_path / "a.mp3"], "$title")


def test_swap_within_selection_is_allowed(
    tmp_path: Path, fake_tags: dict[str, TagData]
) -> None:
    (tmp_path / "A.mp3").write_bytes(b"a")
    (tmp_path / "B.mp3").write_bytes(b"b")
    fake_tags["A.mp3"] = TagData(title="B")
    fake_tags["B.mp3"] = TagData(title="A")
    items = build_template_rename([tmp_path / "A.mp3", tmp_path / "B.mp3"], "$title")
    assert [i.new_name for i in items] == ["B.mp3", "A.mp3"]


def test_unreadable_file_is_skipped(tmp_path: Path, fake_tags: dict[str, TagData]) -> None:
    fake_tags["good.mp3"] = TagData(title="Song")
    items = build_template_rename(
        [tmp_path / "missing-tags.mp3", tmp_path / "good.mp3"], "$title"
    )
    assert [i.new_name for i in items] == ["Song.mp3"]


def test_control_characters_in_tags_are_replaced(
    tmp_path: Path, fake_tags: dict[str, TagData]
) -> None:
    fake_tags["a.mp3"] = TagData(title="Line one\nLine\ttwo")
    items = build_template_rename([tmp_path / "a.mp3"], "$title")
    assert [i.new_name for i in items] == ["Line one_Line_two.mp3"]
