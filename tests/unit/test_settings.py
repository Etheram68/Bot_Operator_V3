"""Tests for Settings configuration."""
import os
import pytest
from bot_operateur.config.settings import Settings


@pytest.fixture
def fake_env(tmp_path):
    """Create a temporary .env file to avoid loading real .env."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "USERNAME=test_user\n"
        "PASSWORD=test_pass\n"
        "GAME_URL=https://test.example.com\n"
        "HEADLESS=false\n"
        "LOG_LEVEL=DEBUG\n"
        "PAGE_LOAD_TIMEOUT=20\n"
        "ELEMENT_WAIT_TIMEOUT=10\n"
        "FAST_TIMEOUT=5\n"
        "SLOW_TIMEOUT=15\n"
        "RETRY_DELAY=1.5\n"
        "MAX_RETRIES=3\n"
        "BROWSER_SLOW_MO=50\n"
        "DEFAULT_STRATEGY=balanced\n"
        "AUTO_DEPLOY=false\n"
        "MIN_CREDITS_THRESHOLD=500\n"
        "MAX_CONCURRENT_MISSIONS=10\n"
        "MISSION_COOLDOWN=10\n"
        "CYCLE_DELAY=30\n"
        "OPTIMIZATION_THRESHOLD=5\n"
        "DEPLOYMENT_THRESHOLD=8\n"
        "PERSONNEL_THRESHOLD=2\n"
    )
    return str(env_file)


class TestSettingsDefaults:
    def test_default_game_url(self):
        s = Settings(username="u", password="p")
        assert s.game_url == "https://www.operateur112.fr"

    def test_default_timeouts(self):
        s = Settings(username="u", password="p")
        assert s.page_load_timeout == 15
        assert s.element_wait_timeout == 5
        assert s.fast_timeout == 3
        assert s.slow_timeout == 12

    def test_default_strategy(self):
        s = Settings(username="u", password="p")
        assert s.default_strategy == "smart_optimized"
        assert s.auto_deploy is True

    def test_default_thresholds(self):
        s = Settings(username="u", password="p")
        assert s.optimization_threshold == 3
        assert s.deployment_threshold == 5
        assert s.personnel_threshold == 1


class TestSettingsFromEnv:
    def test_loads_from_env_file(self, fake_env):
        s = Settings.from_env(fake_env)
        assert s.username == "test_user"
        assert s.password == "test_pass"
        assert s.game_url == "https://test.example.com"

    def test_loads_timeouts(self, fake_env):
        s = Settings.from_env(fake_env)
        assert s.page_load_timeout == 20
        assert s.element_wait_timeout == 10
        assert s.fast_timeout == 5
        assert s.slow_timeout == 15
        assert s.retry_delay == 1.5
        assert s.max_retries == 3

    def test_loads_booleans(self, fake_env):
        s = Settings.from_env(fake_env)
        assert s.headless is False
        assert s.auto_deploy is False

    def test_loads_thresholds(self, fake_env):
        s = Settings.from_env(fake_env)
        assert s.optimization_threshold == 5
        assert s.deployment_threshold == 8
        assert s.personnel_threshold == 2

    def test_nonexistent_env_file_uses_defaults(self, tmp_path, monkeypatch):
        # Clear env vars that might leak from a real .env file
        for key in ["GAME_URL", "PAGE_LOAD_TIMEOUT", "USERNAME", "PASSWORD"]:
            monkeypatch.delenv(key, raising=False)
        s = Settings.from_env(str(tmp_path / "nonexistent.env"))
        assert s.game_url == "https://www.operateur112.fr"
        assert s.page_load_timeout == 15


class TestSettingsValidation:
    def test_valid_credentials(self):
        s = Settings(username="user", password="pass")
        assert s.validate_credentials() is True

    def test_missing_username(self):
        s = Settings(username="", password="pass")
        assert s.validate_credentials() is False

    def test_missing_password(self):
        s = Settings(username="user", password="")
        assert s.validate_credentials() is False

    def test_both_missing(self):
        s = Settings(username="", password="")
        assert s.validate_credentials() is False


class TestSettingsLogConfig:
    def test_log_config_with_file(self):
        s = Settings(username="u", password="p", log_level="DEBUG", log_file="test.log")
        config = s.get_log_config()
        assert config["level"] == "DEBUG"
        assert config["sink"] == "test.log"
        assert "rotation" in config

    def test_log_config_without_file(self):
        s = Settings(username="u", password="p", log_file=None)
        config = s.get_log_config()
        assert "sink" not in config
