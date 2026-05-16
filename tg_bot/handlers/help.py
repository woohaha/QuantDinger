"""/start /help handlers."""
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

router = Router(name="help")


_HELP_TEXT = (
    "📊 <b>QuantDinger AI 篩選 Bot</b>\n\n"
    "支援 A 股（6 位代碼）。所有命令僅在白名單群組生效。\n\n"
    "<b>命令</b>\n"
    "/ai &lt;code&gt;       — 即時 AI 分析（30–90 秒，結果含 Telegraph 連結）\n"
    "/watch &lt;code&gt;    — 加入群共享 watchlist\n"
    "/unwatch &lt;code&gt;  — 從 watchlist 移除\n"
    "/list             — 顯示 watchlist\n"
    "/scan             — 對 watchlist 全跑 AI\n"
    "/help             — 顯示本說明\n\n"
    "範例：<code>/ai 600519</code>"
)


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(_HELP_TEXT, parse_mode="HTML", disable_web_page_preview=True)
