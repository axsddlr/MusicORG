"""Tests for musicorg.core.autotagger."""

from __future__ import annotations

from pathlib import Path

import pytest

from musicorg.core.autotagger import AutoTagger, MatchCandidate


class _Artist:
    def __init__(self, name: str) -> None:
        self.name = name


class _Release:
    def __init__(self, title: str, artists: list[str]) -> None:
        self.title = title
        self.artists = [_Artist(name) for name in artists]


class _ReleaseWithImages:
    def __init__(self, images: list[dict[str, str]]) -> None:
        self.images = images


class TestMatchCandidate:
    def test_match_percent_perfect(self):
        mc = MatchCandidate(distance=0.0)
        assert mc.match_percent == 100.0

    def test_match_percent_worst(self):
        mc = MatchCandidate(distance=1.0)
        assert mc.match_percent == 0.0

    def test_match_percent_partial(self):
        mc = MatchCandidate(distance=0.25)
        assert mc.match_percent == 75.0

    def test_defaults(self):
        mc = MatchCandidate()
        assert mc.source == ""
        assert mc.artist == ""
        assert mc.album == ""
        assert mc.year == 0
        assert mc.tracks == []
        assert mc.raw_match is None


class TestAutoTagger:
    def test_search_album_empty_paths(self):
        at = AutoTagger()
        assert at.search_album([]) == []

    def test_search_item_nonexistent(self, tmp_path: Path):
        at = AutoTagger()
        fake = tmp_path / "nonexistent.mp3"
        assert at.search_item(fake) == []

    def test_apply_match_no_raw(self):
        at = AutoTagger()
        mc = MatchCandidate(raw_match=None)
        assert at.apply_match(["anything.mp3"], mc) is False

    def test_apply_match_non_dict_raw(self):
        at = AutoTagger()
        mc = MatchCandidate(raw_match="not-a-dict")
        assert at.apply_match(["anything.mp3"], mc) is False

    def test_mb_artist_credit(self):
        at = AutoTagger()
        entity = {
            "artist-credit": [
                {"name": "Artist A", "joinphrase": " feat. "},
                {"artist": {"name": "Artist B"}},
            ]
        }
        assert at._mb_artist_credit(entity) == "Artist A feat. Artist B"

    def test_mb_artist_credit_fallback_phrase(self):
        at = AutoTagger()
        entity = {"artist-credit-phrase": "Fallback Artist"}
        assert at._mb_artist_credit(entity) == "Fallback Artist"

    def test_mb_extract_year(self):
        at = AutoTagger()
        assert at._mb_extract_year({"date": "2004-02-01"}) == 2004
        assert at._mb_extract_year({"first-release-date": "1999"}) == 1999
        assert at._mb_extract_year({"date": ""}) == 0

    def test_mb_artwork_urls(self):
        at = AutoTagger()
        rid = "9e0f52d6-87b2-4f57-8df2-d86f0416533a"
        rgid = "2d0f52d6-87b2-4f57-8df2-d86f0416533a"
        urls = at._mb_artwork_urls(rid, rgid)
        assert f"https://coverartarchive.org/release/{rid}/front-500" in urls
        assert f"https://coverartarchive.org/release-group/{rgid}/front" in urls

    def test_discogs_artwork_urls_collects_uri_variants(self):
        at = AutoTagger()
        release = _ReleaseWithImages(
            images=[
                {"uri": "http://img.discogs.com/full.jpg", "uri150": "http://img.discogs.com/150.jpg"},
                {"uri": "http://img.discogs.com/full.jpg"},
            ]
        )
        urls = at._discogs_artwork_urls(release)
        assert "http://img.discogs.com/150.jpg" in urls
        assert "http://img.discogs.com/full.jpg" in urls
        assert len(urls) == 2

    def test_expand_artwork_urls_adds_https_and_coverart_fallback(self):
        at = AutoTagger()
        urls = at._expand_artwork_urls(
            ["http://coverartarchive.org/release/abc/front-500"]
        )
        assert "http://coverartarchive.org/release/abc/front-500" in urls
        assert "https://coverartarchive.org/release/abc/front-500" in urls
        assert "http://coverartarchive.org/release/abc/front" in urls
        assert "https://coverartarchive.org/release/abc/front" in urls

    def test_discogs_distance(self):
        at = AutoTagger()
        close = _Release("The Dark Side of the Moon", ["Pink Floyd"])
        far = _Release("Random Comp", ["Unknown Artist"])

        close_score = at._discogs_distance("Pink Floyd", "Dark Side of the Moon", close)
        far_score = at._discogs_distance("Pink Floyd", "Dark Side of the Moon", far)

        assert 0.0 <= close_score <= 1.0
        assert 0.0 <= far_score <= 1.0
        assert close_score < far_score

    def test_parse_duration(self):
        at = AutoTagger()
        assert at._parse_duration("3:45") == 225
        assert at._parse_duration("1:02:03") == 3723
        assert at._parse_duration("") == 0
        assert at._parse_duration("bad") == 0

    def test_parse_discogs_position(self):
        at = AutoTagger()
        assert at._parse_discogs_position("A1") == (1, 1)
        assert at._parse_discogs_position("1-3") == (1, 3)
        assert at._parse_discogs_position("7", default_disc=2) == (2, 7)
        assert at._parse_discogs_position("CD1-03") == (1, 1)

    def test_search_album_with_diagnostics_keeps_discogs_on_mb_failure(self, monkeypatch):
        at = AutoTagger(discogs_token="token")
        discogs_candidate = MatchCandidate(source="Discogs", album="Parachutes", distance=0.2)

        monkeypatch.setattr(
            at,
            "_resolve_hints_from_files",
            lambda paths, artist_hint, album_hint: ("Coldplay", "Parachutes"),
        )
        monkeypatch.setattr(
            at,
            "_search_album_mb",
            lambda artist, album: (_ for _ in ()).throw(RuntimeError("mb network reset")),
        )
        monkeypatch.setattr(
            at,
            "_search_album_discogs",
            lambda artist, album: [discogs_candidate],
        )

        payload = at.search_album_with_diagnostics(["dummy.mp3"])
        assert payload["candidates"] == [discogs_candidate]
        assert payload["source_counts"]["MusicBrainz"] == 0
        assert payload["source_counts"]["Discogs"] == 1
        assert "MusicBrainz" in payload["source_errors"]
        assert "network reset" in payload["source_errors"]["MusicBrainz"]

    def test_search_item_with_diagnostics_keeps_discogs_on_mb_failure(
        self,
        tmp_path: Path,
        monkeypatch,
    ):
        at = AutoTagger(discogs_token="token")
        target = tmp_path / "song.mp3"
        target.write_bytes(b"")
        discogs_candidate = MatchCandidate(source="Discogs", album="Parachutes", distance=0.2)

        monkeypatch.setattr(
            at,
            "_search_item_mb",
            lambda artist, title: (_ for _ in ()).throw(RuntimeError("mb timeout")),
        )
        monkeypatch.setattr(
            at,
            "_search_item_discogs",
            lambda artist, title: [discogs_candidate],
        )

        payload = at.search_item_with_diagnostics(
            target,
            artist_hint="Coldplay",
            title_hint="Yellow",
        )
        assert payload["candidates"] == [discogs_candidate]
        assert payload["source_counts"]["MusicBrainz"] == 0
        assert payload["source_counts"]["Discogs"] == 1
        assert "MusicBrainz" in payload["source_errors"]
        assert "timeout" in payload["source_errors"]["MusicBrainz"]

    def test_search_album_with_diagnostics_raises_when_all_sources_fail(self, monkeypatch):
        at = AutoTagger()

        monkeypatch.setattr(
            at,
            "_resolve_hints_from_files",
            lambda paths, artist_hint, album_hint: ("Coldplay", "Parachutes"),
        )
        monkeypatch.setattr(
            at,
            "_search_album_mb",
            lambda artist, album: (_ for _ in ()).throw(RuntimeError("mb down")),
        )

        with pytest.raises(RuntimeError, match="MusicBrainz: mb down"):
            at.search_album_with_diagnostics(["dummy.mp3"])

    def test_search_album_with_diagnostics_retries_transient_mb_errors(self, monkeypatch):
        at = AutoTagger()
        attempts = {"count": 0}
        expected = MatchCandidate(source="MusicBrainz", album="Retried", distance=0.1)

        monkeypatch.setattr(
            at,
            "_resolve_hints_from_files",
            lambda paths, artist_hint, album_hint: ("Artist", "Album"),
        )

        def _mb_once_then_success(artist, album):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("urlopen error [WinError 10054] An existing connection was forcibly closed")
            return [expected]

        monkeypatch.setattr(at, "_search_album_mb", _mb_once_then_success)

        payload = at.search_album_with_diagnostics(["dummy.mp3"])
        assert payload["candidates"] == [expected]
        assert payload["source_errors"] == {}
        assert attempts["count"] == 2

    def test_guess_image_mime(self):
        at = AutoTagger()
        assert at._guess_image_mime(b"\xFF\xD8\xFFtest") == "image/jpeg"
        assert at._guess_image_mime(b"\x89PNG\r\n\x1a\n123") == "image/png"
