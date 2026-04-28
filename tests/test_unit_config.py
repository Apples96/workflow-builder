"""
Unit tests for application configuration.

Tests the Settings contract: default values, env var overrides, and validation.
"""

import pytest

pytestmark = pytest.mark.unit


class TestSettings:
    """Tests for the Settings configuration class."""

    def _make_settings(self, monkeypatch, **env_vars):
        """Create a fresh Settings instance with the given env vars."""
        # Clear any existing keys that might leak from the real env
        for key in ["ANTHROPIC_API_KEY", "LIGHTON_API_KEY", "DEBUG", "HOST",
                     "PORT", "VERCEL", "MAX_CELL_EXECUTION_TIME"]:
            monkeypatch.delenv(key, raising=False)
        # Set requested vars
        for k, v in env_vars.items():
            monkeypatch.setenv(k, v)
        # Import fresh (Settings reads os.getenv in __init__)
        from api.config import Settings
        return Settings()

    def test_defaults(self, monkeypatch):
        """Settings have sensible defaults when no env vars are set."""
        s = self._make_settings(monkeypatch)
        assert s.host == "0.0.0.0"
        assert s.port == 8000
        assert s.debug is False
        assert s.max_cell_execution_time == 300
        assert s.anthropic_api_key == ""

    def test_env_overrides(self, monkeypatch):
        """Settings pick up values from environment variables."""
        s = self._make_settings(
            monkeypatch,
            HOST="127.0.0.1",
            PORT="9000",
            MAX_CELL_EXECUTION_TIME="60",
        )
        assert s.host == "127.0.0.1"
        assert s.port == 9000
        assert s.max_cell_execution_time == 60

    def test_validate_missing_key_raises(self, monkeypatch):
        """validate() raises ValueError when ANTHROPIC_API_KEY is empty."""
        s = self._make_settings(monkeypatch)
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            s.validate()

    def test_validate_with_key_passes(self, monkeypatch):
        """validate() passes when ANTHROPIC_API_KEY is set."""
        s = self._make_settings(monkeypatch, ANTHROPIC_API_KEY="sk-test")
        s.validate()  # should not raise

    def test_debug_and_vercel_booleans(self, monkeypatch):
        """Boolean flags parse correctly from string env vars."""
        s = self._make_settings(monkeypatch, DEBUG="true", VERCEL="1")
        assert s.debug is True
        assert s.is_vercel is True
