"""Test config loading from env."""
import pytest
from pydantic import ValidationError

from tg_bot.config import Settings


def test_parses_required_env(monkeypatch):
    monkeypatch.setenv("TG_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("WHITELIST_GROUP_IDS", "-100111,-100222")
    monkeypatch.setenv("WHITELIST_USER_IDS", "111,222,333")
    monkeypatch.setenv("QUANTDINGER_API_URL", "http://backend:5000")
    monkeypatch.setenv("QUANTDINGER_USERNAME", "user")
    monkeypatch.setenv("QUANTDINGER_PASSWORD", "pw")

    s = Settings()

    assert s.tg_bot_token == "123:abc"
    assert s.whitelist_group_ids == {-100111, -100222}
    assert s.whitelist_user_ids == {111, 222, 333}
    assert str(s.quantdinger_api_url).rstrip("/") == "http://backend:5000"
    assert s.telegraph_author_name == "QuantDinger Bot"   # default
    assert s.telegraph_reuse_page is False
    assert s.db_path.name == "bot.db"


def test_missing_required_raises(monkeypatch):
    for key in ("TG_BOT_TOKEN", "WHITELIST_GROUP_IDS", "WHITELIST_USER_IDS",
                "QUANTDINGER_API_URL", "QUANTDINGER_USERNAME", "QUANTDINGER_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValidationError):
        Settings()


def test_telegraph_optional(monkeypatch):
    for key in ("TG_BOT_TOKEN", "WHITELIST_GROUP_IDS", "WHITELIST_USER_IDS",
                "QUANTDINGER_API_URL", "QUANTDINGER_USERNAME", "QUANTDINGER_PASSWORD"):
        monkeypatch.setenv(key, "x" if "URL" not in key else "http://backend:5000")
    monkeypatch.setenv("WHITELIST_GROUP_IDS", "-100111")
    monkeypatch.setenv("WHITELIST_USER_IDS", "111")
    monkeypatch.setenv("TELEGRAPH_ACCESS_TOKEN", "")
    s = Settings()
    assert s.telegraph_access_token is None or s.telegraph_access_token == ""
