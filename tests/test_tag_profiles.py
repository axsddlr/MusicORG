"""AutoTagProfile serialization: new fields, legacy overwrite_fields migration."""

from __future__ import annotations

from musicorg.core.tag_profiles import AutoTagProfile, ProfileStore


def test_round_trip_with_new_fields(tmp_path):
    p = AutoTagProfile(
        name="P",
        enabled_sources=["MusicBrainz", "Beatport"],
        overwrite_fields=["title", "genre"],
        fill_empty_only=False,
        regex_cleanup_pattern=r"\s+\(x\)",
        regex_cleanup_replacement="y",
        min_match_pct=75,
        merge_genres=True,
        id3_v23=True,
    )
    store = ProfileStore(tmp_path)
    store.save_autotag_profiles([p, AutoTagProfile(name="All", overwrite_fields=None)])
    loaded = store.load_autotag_profiles()
    assert loaded[0] == p
    assert loaded[1].overwrite_fields is None


def test_legacy_empty_overwrite_fields_means_all():
    assert AutoTagProfile.from_dict({"name": "L", "overwrite_fields": []}).overwrite_fields is None


def test_missing_new_keys_get_defaults():
    p = AutoTagProfile.from_dict({"name": "Old"})
    assert p.overwrite_fields is None
    assert p.min_match_pct == 0
    assert p.merge_genres is False
    assert p.id3_v23 is False
    assert AutoTagProfile().overwrite_fields is None


def test_default_profile_does_not_fill_empty_only(tmp_path):
    assert AutoTagProfile().fill_empty_only is False
    assert ProfileStore(tmp_path).load_autotag_profiles()[0].fill_empty_only is False
    assert AutoTagProfile.from_dict({"name": "S", "fill_empty_only": True}).fill_empty_only is True


def test_corrupt_profiles_file_is_moved_aside(tmp_path, caplog):
    store = ProfileStore(tmp_path)
    bad = tmp_path / "autotag_profiles.json"
    bad.write_text("{not json", encoding="utf-8")
    with caplog.at_level("WARNING"):
        loaded = store.load_autotag_profiles()
    assert [p.name for p in loaded] == ["Default"]
    assert "corrupt" in caplog.text.lower()
    aside = list(tmp_path.glob("autotag_profiles.corrupt-*.json"))
    assert len(aside) == 1 and aside[0].read_text(encoding="utf-8") == "{not json"
    store.save_autotag_profiles(loaded)
    assert aside[0].read_text(encoding="utf-8") == "{not json"
