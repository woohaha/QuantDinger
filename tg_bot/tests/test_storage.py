"""Test SQLite storage layer (sync, single-process)."""
import pytest

from tg_bot.services.storage import Storage


@pytest.fixture
def storage(tmp_db_path):
    s = Storage(tmp_db_path)
    s.init_schema()
    yield s
    s.close()


def test_watchlist_add_and_list(storage):
    storage.watchlist_add("600519", "貴州茅台", added_by=111)
    storage.watchlist_add("000001", "平安銀行", added_by=222)
    rows = storage.watchlist_list()
    codes = {r["code"] for r in rows}
    assert codes == {"600519", "000001"}


def test_watchlist_add_dup_is_noop(storage):
    storage.watchlist_add("600519", "貴州茅台", added_by=111)
    storage.watchlist_add("600519", "新名字", added_by=222)   # ignored
    rows = storage.watchlist_list()
    assert len(rows) == 1
    # original name kept
    assert rows[0]["name"] == "貴州茅台"


def test_watchlist_add_backfills_null_name(storage):
    """If a row was inserted with name=None, a later add with a real name fills it in."""
    storage.watchlist_add("600519", None, added_by=111)
    rows = storage.watchlist_list()
    assert rows[0]["name"] is None
    storage.watchlist_add("600519", "貴州茅台", added_by=222)
    rows = storage.watchlist_list()
    assert len(rows) == 1
    assert rows[0]["name"] == "貴州茅台"
    # added_by stays from the original insert (we don't overwrite it)
    assert rows[0]["added_by"] == 111


def test_watchlist_remove(storage):
    storage.watchlist_add("600519", "貴州茅台", added_by=111)
    removed = storage.watchlist_remove("600519")
    assert removed is True
    assert storage.watchlist_list() == []


def test_watchlist_remove_missing_returns_false(storage):
    assert storage.watchlist_remove("999999") is False


def test_watchlist_set_name_updates_existing(storage):
    storage.watchlist_add("600519", None, added_by=111)
    ok = storage.watchlist_set_name("600519", "貴州茅台")
    assert ok is True
    assert storage.watchlist_list()[0]["name"] == "貴州茅台"


def test_watchlist_set_name_missing_returns_false(storage):
    assert storage.watchlist_set_name("999999", "X") is False


def test_auth_cache_roundtrip(storage):
    assert storage.auth_cache_get() is None
    storage.auth_cache_set("token-abc")
    assert storage.auth_cache_get() == "token-abc"
    storage.auth_cache_set("token-xyz")
    assert storage.auth_cache_get() == "token-xyz"


def test_telegraph_account_roundtrip(storage):
    assert storage.telegraph_account_get() is None
    storage.telegraph_account_set(
        access_token="tok",
        short_name="QD",
        author_name="QuantDinger Bot",
        author_url="https://t.me/x",
        auth_url="https://edit.telegra.ph/auth/abc",
    )
    acc = storage.telegraph_account_get()
    assert acc["access_token"] == "tok"
    assert acc["short_name"] == "QD"
    assert acc["author_name"] == "QuantDinger Bot"


def test_telegraph_page_add_and_latest(storage):
    storage.telegraph_page_add(
        code="600519", path="600519-05-16",
        url="https://telegra.ph/600519-05-16",
        title="t", timeframe="1D", decision="BUY")
    storage.telegraph_page_add(
        code="600519", path="600519-05-17",
        url="https://telegra.ph/600519-05-17",
        title="t2", timeframe="1D", decision="SELL")
    latest = storage.telegraph_page_latest("600519")
    assert latest["path"] == "600519-05-17"
    assert latest["decision"] == "SELL"


def test_telegraph_page_latest_missing(storage):
    assert storage.telegraph_page_latest("999999") is None
