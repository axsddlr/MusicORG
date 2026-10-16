"""Swallowed errors must keep their old fallback but leave a log record."""

from __future__ import annotations

import logging
import sqlite3
from unittest.mock import patch

from musicorg.core.beatport_client import BeatportClient
from musicorg.core.library_db import LibraryDatabase
from musicorg.core.traxsource_client import TraxsourceClient
from musicorg.workers import tag_read_worker
from musicorg.workers.tag_read_worker import TagReadWorker


def test_beatport_fetch_failure_logged(caplog):
    with patch("musicorg.core.beatport_client.urlopen", side_effect=OSError("boom")):
        with caplog.at_level(logging.DEBUG):
            assert BeatportClient()._search_tracks("a b") == []
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


def test_traxsource_fetch_failure_logged(caplog):
    with patch("musicorg.core.traxsource_client.urlopen", side_effect=OSError("boom")):
        with caplog.at_level(logging.DEBUG):
            assert TraxsourceClient()._search_tracks("a b") == []
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


def test_library_db_bad_custom_tags_logged(tmp_path, caplog):
    db = LibraryDatabase(tmp_path / "lib.db")
    db.open()
    try:
        db._conn.execute("PRAGMA foreign_keys=OFF")
        db._conn.execute(
            "INSERT INTO tracks (album_id, path, format, custom_tags) VALUES (1, ?, ?, ?)", ("x.mp3", "mp3", "{not json")
        )
        db._conn.commit()
        with caplog.at_level(logging.DEBUG):
            assert db.list_custom_tag_keys() == []
    finally:
        db.close()
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


def test_tag_read_worker_cache_open_failure_logged(tmp_path, caplog):
    worker = TagReadWorker([], cache_db_path=str(tmp_path / "c.db"))
    with patch.object(tag_read_worker, "TagCache", side_effect=sqlite3.Error("bad")):
        with caplog.at_level(logging.DEBUG):
            assert worker._thread_cache() is None
    assert any(r.levelno >= logging.ERROR for r in caplog.records)
