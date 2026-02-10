"""Tests for musicorg.core.beets_config."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from musicorg.core.beets_config import BeetsConfigManager


@pytest.fixture
def mock_settings(tmp_path):
    settings = MagicMock()
    settings.beets_config_dir.return_value = tmp_path / "beets"
    settings.dest_dir = "/music"
    settings.beets_db_path = str(tmp_path / "beets" / "library.db")
    settings.path_format = "$albumartist/$album/$track $title"
    settings.discogs_token = ""
    return settings


class TestBeetsConfigManager:
    def test_generate_creates_config_file(self, mock_settings):
        mgr = BeetsConfigManager(mock_settings)
        path = mgr.generate()
        assert path.exists()
        assert path.name == "config.yaml"

    def test_generate_valid_yaml(self, mock_settings):
        mgr = BeetsConfigManager(mock_settings)
        path = mgr.generate()
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(config, dict)
        assert config["directory"] == "/music"
        assert config["import"]["copy"] is True
        assert config["paths"]["default"] == "$albumartist/$album/$track $title"

    def test_generate_without_discogs(self, mock_settings):
        mock_settings.discogs_token = ""
        mgr = BeetsConfigManager(mock_settings)
        path = mgr.generate()
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "discogs" not in config.get("plugins", [])

    def test_generate_with_discogs(self, mock_settings):
        mock_settings.discogs_token = "my_token_123"
        mgr = BeetsConfigManager(mock_settings)
        path = mgr.generate()
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "discogs" in config["plugins"]
        assert config["discogs"]["user_token"] == "my_token_123"

    def test_config_dir_created(self, mock_settings, tmp_path):
        cfg_dir = tmp_path / "new_dir" / "beets"
        mock_settings.beets_config_dir.return_value = cfg_dir
        mgr = BeetsConfigManager(mock_settings)
        mgr.generate()
        assert cfg_dir.exists()

    def test_config_path_property(self, mock_settings):
        mgr = BeetsConfigManager(mock_settings)
        assert mgr.config_path.name == "config.yaml"
