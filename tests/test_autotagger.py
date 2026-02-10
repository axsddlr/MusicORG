"""Tests for musicorg.core.autotagger."""

import pytest
from collections import namedtuple

from musicorg.core.autotagger import AutoTagger, MatchCandidate


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
        results = at.search_album([])
        assert results == []

    def test_search_item_nonexistent(self, tmp_path):
        at = AutoTagger()
        fake = tmp_path / "nonexistent.mp3"
        results = at.search_item(fake)
        assert results == []

    def test_apply_match_no_raw(self, tmp_path):
        at = AutoTagger()
        mc = MatchCandidate(raw_match=None)
        result = at.apply_match([], mc)
        assert result is False

    def test_extract_candidates_from_proposal_like(self):
        at = AutoTagger()
        ProposalLike = namedtuple("ProposalLike", ["candidates"])
        proposal = ProposalLike(candidates=["a", "b"])
        assert at._extract_candidates(proposal) == ["a", "b"]

    def test_extract_candidates_from_legacy_album_tuple(self):
        at = AutoTagger()
        result = ("artist", "album", ["c1", "c2"], "recommended")
        assert at._extract_candidates(result) == ["c1", "c2"]

    def test_extract_candidates_from_modern_album_tuple(self):
        at = AutoTagger()
        ProposalLike = namedtuple("ProposalLike", ["candidates"])
        result = ("artist", "album", ProposalLike(candidates=["x"]))
        assert at._extract_candidates(result) == ["x"]

    def test_candidate_artwork_urls_discogs_cover(self):
        at = AutoTagger()
        info = type(
            "Info",
            (),
            {
                "cover_art_url": "https://i.discogs.com/cover.jpg",
                "data_source": "Discogs",
                "data_url": "",
                "album_id": "",
                "releasegroup_id": "",
            },
        )()
        urls = at._candidate_artwork_urls(info)
        assert urls[0] == "https://i.discogs.com/cover.jpg"

    def test_candidate_artwork_urls_musicbrainz_release(self):
        at = AutoTagger()
        rid = "9e0f52d6-87b2-4f57-8df2-d86f0416533a"
        info = type(
            "Info",
            (),
            {
                "cover_art_url": "",
                "data_source": "MusicBrainz",
                "data_url": f"https://musicbrainz.org/release/{rid}",
                "album_id": "",
                "releasegroup_id": "",
            },
        )()
        urls = at._candidate_artwork_urls(info)
        assert f"https://coverartarchive.org/release/{rid}/front-500" in urls
        assert f"https://coverartarchive.org/release/{rid}/front" in urls

    def test_guess_image_mime(self):
        at = AutoTagger()
        assert at._guess_image_mime(b"\xFF\xD8\xFFtest") == "image/jpeg"
        assert at._guess_image_mime(b"\x89PNG\r\n\x1a\n123") == "image/png"
