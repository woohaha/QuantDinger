"""Test WhitelistMiddleware."""
from types import SimpleNamespace

import pytest

from tg_bot.middlewares.whitelist import WhitelistMiddleware


@pytest.fixture
def mw():
    return WhitelistMiddleware(allowed_group_ids={-100111}, allowed_user_ids={111, 222})


def _make_event(chat_id: int, user_id: int, chat_type: str = "supergroup"):
    """Mock aiogram TelegramObject with chat + from_user."""
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id, type=chat_type),
        from_user=SimpleNamespace(id=user_id),
        answer=AsyncRecorder(),
    )


class AsyncRecorder:
    def __init__(self):
        self.calls = []
    async def __call__(self, text, **kw):
        self.calls.append((text, kw))


async def _handler_noop(event, data):
    data.setdefault("handler_called", True)
    return "ok"


async def test_allows_whitelisted_combo(mw):
    event = _make_event(chat_id=-100111, user_id=111)
    data: dict = {}
    result = await mw(_handler_noop, event, data)
    assert result == "ok"
    assert data.get("handler_called") is True


async def test_silently_blocks_unknown_group(mw):
    event = _make_event(chat_id=-100999, user_id=111)
    data: dict = {}
    result = await mw(_handler_noop, event, data)
    assert result is None
    assert "handler_called" not in data


async def test_blocks_unknown_user_in_known_group(mw):
    event = _make_event(chat_id=-100111, user_id=999)
    data: dict = {}
    result = await mw(_handler_noop, event, data)
    # Unknown user gets a polite reply (not silent), per spec §10
    assert result is None
    assert len(event.answer.calls) == 1
    assert "白名單" in event.answer.calls[0][0]


async def test_blocks_private_chat(mw):
    event = _make_event(chat_id=111, user_id=111, chat_type="private")
    data: dict = {}
    result = await mw(_handler_noop, event, data)
    assert result is None
    assert len(event.answer.calls) == 1
    assert "群組" in event.answer.calls[0][0]


async def test_handles_event_without_user(mw):
    """Some updates (e.g. channel posts) have no from_user."""
    event = SimpleNamespace(chat=SimpleNamespace(id=-100111, type="supergroup"),
                            from_user=None, answer=AsyncRecorder())
    data: dict = {}
    result = await mw(_handler_noop, event, data)
    assert result is None
