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
async def cmd_watch(msg: Message, storage: Storage, quantdinger):
    try:
        code = parse_code(msg.text or "")
    except ValueError as e:
        await _err(msg, str(e))
        return
    # Best-effort name lookup; on any failure the row still gets added with
    # name=None (later /ai or /scan can backfill it via run_analysis).
    name = await quantdinger.get_symbol_name(market="CNStock", symbol=code)
    storage.watchlist_add(code, name=name, added_by=msg.from_user.id)
    label = f"<code>{code}</code>" + (f"  {name}" if name else "")
    await msg.answer(f"✅ 已加入 watchlist：{label}", parse_mode="HTML")


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


@router.message(Command("scan"))
async def cmd_scan(msg: Message,
                   storage: Storage,
                   quantdinger,                          # QuantDingerClient
                   telegraph,                            # TelegraphClient
                   telegraph_author_name: str,
                   telegraph_author_url: str,
                   reuse_page: bool):
    import asyncio
    from tg_bot.handlers.analyze import run_analysis, _timeframe_keyboard
    from tg_bot.services.quantdinger import BackendError

    rows = storage.watchlist_list()
    if not rows:
        await msg.answer("📭 Watchlist 為空，沒東西可掃。", parse_mode="HTML")
        return

    await msg.answer(f"🔁 開始 /scan，共 {len(rows)} 檔...", parse_mode="HTML")

    for r in rows:
        code = r["code"]
        try:
            banner, _ = await run_analysis(
                code=code, name=r.get("name"), timeframe="1D",
                storage=storage, quantdinger=quantdinger, telegraph=telegraph,
                telegraph_author_name=telegraph_author_name,
                telegraph_author_url=telegraph_author_url,
                reuse_page=reuse_page,
            )
            await msg.answer(banner, parse_mode="HTML",
                             disable_web_page_preview=False,
                             reply_markup=_timeframe_keyboard(code))
        except BackendError as e:
            await msg.answer(f"❌ {code} 分析失敗：{e}", parse_mode="HTML")
        except Exception as e:
            await msg.answer(f"❌ {code} 異常：{type(e).__name__}: {e}",
                             parse_mode="HTML")
        await asyncio.sleep(2)
