"""/ai handler + reusable run_analysis() helper.

run_analysis(): pure orchestration, all I/O via injected clients — easy to test.
cmd_ai():       aiogram glue around run_analysis().
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from tg_bot.handlers.watchlist import parse_code
from tg_bot.services.banner import build_banner
from tg_bot.services.page_builder import build_page_content, build_page_title
from tg_bot.services.quantdinger import BackendError, QuantDingerClient
from tg_bot.services.storage import Storage
from tg_bot.services.telegraph import TelegraphClient, TelegraphError

router = Router(name="analyze")


async def run_analysis(*, code: str, name: str | None, timeframe: str,
                       storage: Storage, quantdinger: QuantDingerClient,
                       telegraph: TelegraphClient,
                       telegraph_author_name: str,
                       telegraph_author_url: str,
                       reuse_page: bool) -> tuple[str, str]:
    """Run the full analysis flow and return (banner_html, telegraph_url).

    Raises BackendError if the backend call fails (caller decides how to render).
    Telegraph failures are swallowed — banner is returned with a degraded note
    and url is "".
    """
    payload = await quantdinger.analyze(
        market="CNStock", symbol=code, language="zh-TW", timeframe=timeframe,
    )

    title = build_page_title(payload, name=name)
    content = build_page_content(payload, name=name)

    page_url = ""
    page_path = ""
    try:
        if reuse_page:
            existing = storage.telegraph_page_latest(code)
            if existing:
                result = await telegraph.edit_page(
                    path=existing["path"], title=title, content=content,
                    author_name=telegraph_author_name,
                    author_url=telegraph_author_url,
                )
            else:
                result = await telegraph.create_page(
                    title=title, content=content,
                    author_name=telegraph_author_name,
                    author_url=telegraph_author_url,
                )
        else:
            result = await telegraph.create_page(
                title=title, content=content,
                author_name=telegraph_author_name,
                author_url=telegraph_author_url,
            )
        page_url = str(result.get("url") or "")
        page_path = str(result.get("path") or "")
    except TelegraphError:
        # Degraded — banner will display a failure note
        pass

    if page_path:
        storage.telegraph_page_add(
            code=code, path=page_path, url=page_url, title=title,
            timeframe=timeframe, decision=str(payload.get("decision") or "").upper(),
        )

    if page_url:
        banner = build_banner(payload, name=name, telegraph_url=page_url)
    else:
        banner = (
            build_banner(payload, name=name, telegraph_url="about:blank")
            + "\n\n⚠️ <i>詳細報告生成失敗，請稍後 /ai 重試</i>"
        )

    return banner, page_url


def _timeframe_keyboard(code: str):
    kb = InlineKeyboardBuilder()
    for tf, label in (("1H", "切 1H"), ("4H", "切 4H"),
                      ("1W", "切 1W"), ("1D", "刷新")):
        kb.button(text=label, callback_data=f"tf:{code}:{tf}")
    kb.adjust(4)
    return kb.as_markup()


@router.message(Command("ai"))
async def cmd_ai(msg: Message,
                 storage: Storage,
                 quantdinger: QuantDingerClient,
                 telegraph: TelegraphClient,
                 telegraph_author_name: str,
                 telegraph_author_url: str,
                 reuse_page: bool):
    try:
        code = parse_code(msg.text or "")
    except ValueError as e:
        await msg.answer(f"❌ {e}\n用法：<code>/ai 600519</code>",
                         parse_mode="HTML")
        return

    pending = await msg.answer(f"🔍 正在分析 <code>{code}</code>...（約 30–90 秒）",
                                parse_mode="HTML")

    # Look up name from watchlist if present
    name = None
    for r in storage.watchlist_list():
        if r["code"] == code:
            name = r["name"]
            break

    try:
        banner, _url = await run_analysis(
            code=code, name=name, timeframe="1D",
            storage=storage, quantdinger=quantdinger, telegraph=telegraph,
            telegraph_author_name=telegraph_author_name,
            telegraph_author_url=telegraph_author_url,
            reuse_page=reuse_page,
        )
    except BackendError as e:
        await pending.edit_text(f"❌ 分析失敗：{e}", parse_mode="HTML")
        return
    except Exception as e:    # network / unexpected
        await pending.edit_text(f"❌ 分析異常：{type(e).__name__}: {e}",
                                parse_mode="HTML")
        return

    await pending.edit_text(banner, parse_mode="HTML",
                             disable_web_page_preview=False,
                             reply_markup=_timeframe_keyboard(code))
