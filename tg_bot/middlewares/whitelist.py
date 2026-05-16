"""Aiogram middleware: enforce group_id + user_id whitelist."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class WhitelistMiddleware(BaseMiddleware):
    """Drops events that aren't from a (whitelisted group, whitelisted user).

    Behaviour matches spec §10:
      - non-whitelisted group  → silent drop
      - whitelisted group, non-whitelisted user → polite reply
      - private chat → polite reply
      - event without chat/user → silent drop
    """

    def __init__(self, allowed_group_ids: set[int], allowed_user_ids: set[int]):
        super().__init__()
        self.groups = set(allowed_group_ids)
        self.users = set(allowed_user_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Message has `.chat`; CallbackQuery reaches it via `.message.chat`.
        chat = getattr(event, "chat", None)
        if chat is None:
            inner = getattr(event, "message", None)
            chat = getattr(inner, "chat", None) if inner else None
        user = getattr(event, "from_user", None)

        if chat is None or user is None:
            return None

        chat_type = getattr(chat, "type", "")
        if chat_type == "private":
            answer = getattr(event, "answer", None)
            if answer:
                await answer("本 bot 只在指定群組工作")
            return None

        if chat.id not in self.groups:
            return None        # silent

        if user.id not in self.users:
            answer = getattr(event, "answer", None)
            if answer:
                await answer("你不在白名單，找管理員加你")
            return None

        return await handler(event, data)
