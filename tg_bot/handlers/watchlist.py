"""/watch /unwatch /list handlers (and /scan added in Task 12)."""
import re

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from tg_bot.services.storage import Storage

router = Router(name="watchlist")

_CODE_RE = re.compile(r"^\d{6}$")


def parse_code(text: str) -> str:
    """Extract the 6-digit code from a command message text. Raises ValueError."""
    parts = (text or "").strip().split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        raise ValueError("缺少代碼")
    code = parts[1].strip().split()[0]
    if not _CODE_RE.match(code):
        raise ValueError("代碼必須為 6 位數字")
    return code


async def _err(msg: Message, text: str):
    await msg.answer(f"❌ {text}\n用法：<code>/ai 600519</code>", parse_mode="HTML")


@router.message(Command("watch"))
async def cmd_watch(msg: Message, storage: Storage):
    try:
        code = parse_code(msg.text or "")
    except ValueError as e:
        await _err(msg, str(e))
        return
    storage.watchlist_add(code, name=None, added_by=msg.from_user.id)
    await msg.answer(f"✅ 已加入 watchlist：<code>{code}</code>", parse_mode="HTML")


@router.message(Command("unwatch"))
async def cmd_unwatch(msg: Message, storage: Storage):
    try:
        code = parse_code(msg.text or "")
    except ValueError as e:
        await _err(msg, str(e))
        return
    removed = storage.watchlist_remove(code)
    if removed:
        await msg.answer(f"✅ 已移除：<code>{code}</code>", parse_mode="HTML")
    else:
        await msg.answer(f"⚠️ 不在 watchlist：<code>{code}</code>", parse_mode="HTML")


@router.message(Command("list"))
async def cmd_list(msg: Message, storage: Storage):
    rows = storage.watchlist_list()
    if not rows:
        await msg.answer("📭 Watchlist 為空。用 <code>/watch 600519</code> 加入。",
                         parse_mode="HTML")
        return
    lines = ["📋 <b>群共享 Watchlist</b>"]
    for r in rows:
        name = r["name"] or "—"
        lines.append(f"• <code>{r['code']}</code>  {name}")
    await msg.answer("\n".join(lines), parse_mode="HTML")
