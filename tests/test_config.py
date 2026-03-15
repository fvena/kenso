"""Tests for kenso.config."""

from __future__ import annotations

import os

import pytest

from kenso.config import KensoConfig


class TestKensoConfigDefaults:
    def test_default_values(self):
        cfg = KensoConfig()
        assert cfg.database_url is None
        assert cfg.database_source == ""
        assert cfg.transport == "stdio"
        assert cfg.host == "127.0.0.1"
        assert cfg.port == "8000"
        assert cfg.content_preview_chars == 200
        assert cfg.chunk_size == 4000
        assert cfg.chunk_overlap == 0
        assert cfg.search_limit_max == 20
        assert cfg.log_level == "INFO"

    def test_frozen(self):
        cfg = KensoConfig()
        with pytest.raises(AttributeError):
            cfg.transport = "sse"


class TestKensoConfigFromEnv:
    def test_defaults_from_env(self, monkeypatch, tmp_path):
        """Without env var or .kenso/ dir, defaults to .kenso/docs.db in cwd."""
        monkeypatch.delenv("KENSO_DATABASE_URL", raising=False)
        monkeypatch.delenv("KENSO_TRANSPORT", raising=False)
        monkeypatch.chdir(tmp_path)
        # Ensure no global DB is found
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")
        cfg = KensoConfig.from_env()
        assert cfg.transport == "stdio"
        assert cfg.database_url == str(tmp_path / ".kenso" / "docs.db")
        assert cfg.database_source == "local project database"

    def test_custom_database_url(self, monkeypatch):
        monkeypatch.setenv("KENSO_DATABASE_URL", "/tmp/test.db")
        cfg = KensoConfig.from_env()
        assert cfg.database_url == "/tmp/test.db"
        assert cfg.database_source == "KENSO_DATABASE_URL"

    def test_local_kenso_dir(self, monkeypatch, tmp_path):
        """When .kenso/ exists in cwd, use it."""
        monkeypatch.delenv("KENSO_DATABASE_URL", raising=False)
        (tmp_path / ".kenso").mkdir()
        monkeypatch.chdir(tmp_path)
        cfg = KensoConfig.from_env()
        assert cfg.database_url == str(tmp_path / ".kenso" / "docs.db")
        assert cfg.database_source == "local project database"

    def test_global_fallback(self, monkeypatch, tmp_path):
        """When no .kenso/ and global DB exists, use global."""
        monkeypatch.delenv("KENSO_DATABASE_URL", raising=False)
        monkeypatch.chdir(tmp_path)
        global_dir = tmp_path / "fakehome" / ".local" / "share" / "kenso"
        global_dir.mkdir(parents=True)
        (global_dir / "docs.db").touch()
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")
        cfg = KensoConfig.from_env()
        assert cfg.database_url == str(global_dir / "docs.db")
        assert cfg.database_source == "global database"

    def test_env_var_wins_over_local(self, monkeypatch, tmp_path):
        """KENSO_DATABASE_URL takes precedence over .kenso/ dir."""
        monkeypatch.setenv("KENSO_DATABASE_URL", "/tmp/override.db")
        (tmp_path / ".kenso").mkdir()
        monkeypatch.chdir(tmp_path)
        cfg = KensoConfig.from_env()
        assert cfg.database_url == "/tmp/override.db"
        assert cfg.database_source == "KENSO_DATABASE_URL"

    def test_invalid_transport(self, monkeypatch):
        monkeypatch.setenv("KENSO_TRANSPORT", "grpc")
        with pytest.raises(ValueError, match="Invalid transport"):
            KensoConfig.from_env()

    def test_valid_transports(self, monkeypatch):
        for t in ("stdio", "sse", "streamable-http"):
            monkeypatch.setenv("KENSO_TRANSPORT", t)
            cfg = KensoConfig.from_env()
            assert cfg.transport == t

    def test_numeric_settings(self, monkeypatch):
        monkeypatch.setenv("KENSO_CHUNK_SIZE", "8000")
        monkeypatch.setenv("KENSO_CHUNK_OVERLAP", "100")
        monkeypatch.setenv("KENSO_CONTENT_PREVIEW_CHARS", "500")
        monkeypatch.setenv("KENSO_SEARCH_LIMIT_MAX", "50")
        cfg = KensoConfig.from_env()
        assert cfg.chunk_size == 8000
        assert cfg.chunk_overlap == 100
        assert cfg.content_preview_chars == 500
        assert cfg.search_limit_max == 50
