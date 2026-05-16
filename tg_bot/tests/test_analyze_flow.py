"""Test the high-level analyze flow: run_analysis(code, ...) end-to-end with
all external deps mocked. We test the orchestration, not aiogram routing.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.handlers.analyze import run_analysis


@pytest.fixture
def storage_mock():
    m = MagicMock()
    m.telegraph_page_latest.return_value = None
    return m


@pytest.fixture
def qd_mock(fake_analysis_json):
    m = MagicMock()
    m.analyze = AsyncMock(return_value=fake_analysis_json)
    return m


@pytest.fixture
def tg_mock():
    m = MagicMock()
    m.create_page = AsyncMock(return_value={
        "path": "601766-05-16",
        "url": "https://telegra.ph/601766-05-16",
    })
    m.edit_page = AsyncMock()
    return m


async def test_happy_path_creates_page_and_returns_banner(
        storage_mock, qd_mock, tg_mock, fake_analysis_json):
    banner, url = await run_analysis(
        code="601766", name="中國中車", timeframe="1D",
        storage=storage_mock, quantdinger=qd_mock, telegraph=tg_mock,
        telegraph_author_name="QD", telegraph_author_url="",
        reuse_page=False,
    )
    qd_mock.analyze.assert_awaited_once_with(
        market="CNStock", symbol="601766", language="zh-TW", timeframe="1D")
    tg_mock.create_page.assert_awaited_once()
    tg_mock.edit_page.assert_not_awaited()
    storage_mock.telegraph_page_add.assert_called_once()
    storage_mock.watchlist_list.assert_not_called()    # not part of /ai
    assert url == "https://telegra.ph/601766-05-16"
    assert "中國中車" in banner
    assert "BUY" in banner
    assert "https://telegra.ph/601766-05-16" in banner


async def test_reuse_page_calls_edit_when_prior_exists(
        storage_mock, qd_mock, tg_mock):
    storage_mock.telegraph_page_latest.return_value = {
        "code": "601766", "path": "601766-old", "url": "https://telegra.ph/601766-old"
    }
    tg_mock.edit_page = AsyncMock(return_value={
        "path": "601766-old", "url": "https://telegra.ph/601766-old"
    })
    banner, url = await run_analysis(
        code="601766", name="中國中車", timeframe="1D",
        storage=storage_mock, quantdinger=qd_mock, telegraph=tg_mock,
        telegraph_author_name="QD", telegraph_author_url="",
        reuse_page=True,
    )
    tg_mock.edit_page.assert_awaited_once()
    tg_mock.create_page.assert_not_awaited()
    assert url == "https://telegra.ph/601766-old"


async def test_telegraph_failure_returns_degraded_banner(
        storage_mock, qd_mock, fake_analysis_json):
    from tg_bot.services.telegraph import TelegraphError
    tg = MagicMock()
    tg.create_page = AsyncMock(side_effect=TelegraphError("ACCESS_TOKEN_INVALID"))
    tg.edit_page = AsyncMock(side_effect=TelegraphError("ACCESS_TOKEN_INVALID"))

    banner, url = await run_analysis(
        code="601766", name="中國中車", timeframe="1D",
        storage=storage_mock, quantdinger=qd_mock, telegraph=tg,
        telegraph_author_name="QD", telegraph_author_url="",
        reuse_page=False,
    )
    assert url == ""
    # Banner still has the core fields plus an explicit failure note
    assert "BUY" in banner
    assert "詳細報告生成失敗" in banner


async def test_backend_error_bubbles_up(storage_mock, tg_mock):
    from tg_bot.services.quantdinger import BackendError
    qd = MagicMock()
    qd.analyze = AsyncMock(side_effect=BackendError("credits insufficient (need 10, have 3)"))
    with pytest.raises(BackendError):
        await run_analysis(
            code="601766", name=None, timeframe="1D",
            storage=storage_mock, quantdinger=qd, telegraph=tg_mock,
            telegraph_author_name="QD", telegraph_author_url="",
            reuse_page=False,
        )
