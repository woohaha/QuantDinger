"""Bot entry point.

Wires everything: settings → storage → clients → dispatcher → polling.
All clients are passed to handlers via aiogram's `data` dict
(workflow_data mechanism), so handlers receive them as kwargs.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from tg_bot.config import Settings
from tg_bot.handlers import analyze, callbacks, help as help_h, watchlist
from tg_bot.middlewares.whitelist import WhitelistMiddleware
from tg_bot.services.quantdinger import QuantDingerClient
from tg_bot.services.storage import Storage
from tg_bot.services.telegraph import TelegraphClient


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("tg_bot")


async def _bootstrap_telegraph(storage: Storage, settings: Settings) -> TelegraphClient:
    """Return a TelegraphClient with a usable access_token.

    Precedence: env var > sqlite cache > create new account.
    """
    if settings.telegraph_access_token:
        token = settings.telegraph_access_token
    else:
        acc = storage.telegraph_account_get()
        if acc:
            token = acc["access_token"]
        else:
            tmp = TelegraphClient()
            try:
                result = await tmp.create_account(
                    short_name="QuantDinger",
                    author_name=settings.telegraph_author_name,
                    author_url=settings.telegraph_author_url,
                )
            finally:
                await tmp.aclose()
            token = result["access_token"]
            storage.telegraph_account_set(
                access_token=token,
                short_name=result.get("short_name"),
                author_name=result.get("author_name"),
                author_url=result.get("author_url"),
                auth_url=result.get("auth_url"),
            )
            log.info("Telegraph account created. auth_url=%s",
                     result.get("auth_url"))
    return TelegraphClient(access_token=token)


async def main():
    settings = Settings()
    storage = Storage(settings.db_path)
    storage.init_schema()

    qd = QuantDingerClient(
        base_url=str(settings.quantdinger_api_url),
        username=settings.quantdinger_username,
        password=settings.quantdinger_password,
    )
    qd.set_initial_token(storage.auth_cache_get())
    try:
        await qd.login()
        storage.auth_cache_set(qd.token)
        log.info("Backend login OK")
    except Exception as e:
        log.error("Backend login failed at startup: %s", e)

    telegraph = await _bootstrap_telegraph(storage, settings)

    bot = Bot(token=settings.tg_bot_token,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Whitelist middleware on messages + callbacks
    mw = WhitelistMiddleware(allowed_group_ids=settings.whitelist_group_ids,
                             allowed_user_ids=settings.whitelist_user_ids)
    dp.message.outer_middleware(mw)
    dp.callback_query.outer_middleware(mw)

    # Make services available to handlers as kwargs
    dp["storage"] = storage
    dp["quantdinger"] = qd
    dp["telegraph"] = telegraph
    dp["telegraph_author_name"] = settings.telegraph_author_name
    dp["telegraph_author_url"] = settings.telegraph_author_url
    dp["reuse_page"] = settings.telegraph_reuse_page

    dp.include_router(help_h.router)
    dp.include_router(analyze.router)
    dp.include_router(watchlist.router)
    dp.include_router(callbacks.router)

    log.info("Bot starting long polling...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await qd.aclose()
        await telegraph.aclose()
        storage.close()


if __name__ == "__main__":
    asyncio.run(main())
