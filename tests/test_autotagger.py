"""Tests for musicorg.core.autotagger."""

import pytest

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
