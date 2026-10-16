import pytest

from musicorg.core.filename_parser import guess_from_filename, parse_filename


def test_three_part():
    assert parse_filename("01 - Daft Punk - One More Time.mp3", "$track - $artist - $title") == {
        "track": "1", "artist": "Daft Punk", "title": "One More Time"}


def test_keeps_parens():
    r = parse_filename("Artist - Title (Extended Mix).flac", "$artist - $title")
    assert r == {"artist": "Artist", "title": "Title (Extended Mix)"}


def test_hyphenated_artist():
    assert parse_filename("Jay-Z - 99 Problems.mp3", "$artist - $title")["artist"] == "Jay-Z"


def test_no_match():
    assert parse_filename("nothing here.mp3", "$artist - $title") is None


def test_unknown_var():
    with pytest.raises(ValueError, match="bogus"):
        parse_filename("a.mp3", "$bogus - $title")


def test_duplicate_var():
    with pytest.raises(ValueError, match="artist"):
        parse_filename("a - b.mp3", "$artist - $artist")


def test_underscores():
    assert parse_filename("Artist_-_Title.mp3", "$artist - $title") == {"artist": "Artist", "title": "Title"}


def test_track_dot():
    assert parse_filename("07. Song.mp3", "$track. $title") == {"track": "7", "title": "Song"}


def test_guess():
    assert guess_from_filename("01 - A - B.mp3") == {"track": "1", "artist": "A", "title": "B"}
    assert guess_from_filename("A - B.mp3") == {"artist": "A", "title": "B"}
    assert guess_from_filename("zzz.mp3") is None


def test_empty_template():
    with pytest.raises(ValueError, match="empty"):
        parse_filename("a.mp3", "  ")
