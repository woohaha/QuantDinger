"""Inline keyboard callbacks — currently only timeframe switching.

callback_data format: "tf:<code>:<timeframe>"
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from tg_bot.handlers.analyze import run_analysis, _timeframe_keyboard
from tg_bot.services.quantdinger import BackendError, QuantDingerClient
from tg_bot.services.storage import Storage
from tg_bot.services.telegraph import TelegraphClient

router = Router(name="callbacks")


@router.callback_query(F.data.startswith("tf:"))
async def on_timeframe(cb: CallbackQuery,
                       storage: Storage,
                       quantdinger: QuantDingerClient,
                       telegraph: TelegraphClient,
                       telegraph_author_name: str,
                       telegraph_author_url: str,
                       reuse_page: bool):
    try:
        _, code, tf = (cb.data or "").split(":")
    except ValueError:
        await cb.answer("無效操作")
        return

    await cb.answer(f"重新分析 {code} ({tf})...")

    # Show pending state
    await cb.message.edit_text(
        f"🔍 正在以 <b>{tf}</b> 周期分析 <code>{code}</code>...",
        parse_mode="HTML",
    )

    name = None
    for r in storage.watchlist_list():
        if r["code"] == code:
            name = r["name"]
            break

    try:
        banner, _ = await run_analysis(
            code=code, name=name, timeframe=tf,
            storage=storage, quantdinger=quantdinger, telegraph=telegraph,
            telegraph_author_name=telegraph_author_name,
            telegraph_author_url=telegraph_author_url,
            reuse_page=reuse_page,
        )
    except BackendError as e:
        await cb.message.edit_text(f"❌ 分析失敗：{e}", parse_mode="HTML")
        return

    await cb.message.edit_text(banner, parse_mode="HTML",
                                disable_web_page_preview=False,
                                reply_markup=_timeframe_keyboard(code))
