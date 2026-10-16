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
