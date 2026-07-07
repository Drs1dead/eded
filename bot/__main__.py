import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from bot.config import settings
from bot.database import init_db
from bot.handlers import (
    active_tasks,
    chest,
    giveaways,
    menu,
    profile,
    propose,
    referral,
    start,
    support,
)
from bot.handlers.admin import broadcast, channels, gifts, giveaways as admin_gw, moderation, panel, stats, whitelist
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.middlewares.whitelist import WhitelistMiddleware
from bot.schedulers.jobs import setup_scheduler

logger = logging.getLogger(__name__)


async def create_storage():
    from aiogram.fsm.storage.memory import MemoryStorage

    if not settings.redis_url:
        logger.info("Redis URL not set, using MemoryStorage for FSM")
        return MemoryStorage()

    redis = Redis.from_url(settings.redis_url)
    try:
        await redis.ping()
        logger.info("Redis connected, using RedisStorage for FSM")
        return RedisStorage(redis=redis)
    except Exception as exc:
        logger.warning("Redis unavailable (%s), using MemoryStorage for FSM", exc)
        await redis.aclose()
        return MemoryStorage()


async def create_dispatcher() -> Dispatcher:
    storage = await create_storage()
    dp = Dispatcher(storage=storage)

    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
    dp.message.middleware(WhitelistMiddleware())
    dp.callback_query.middleware(WhitelistMiddleware())

    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(giveaways.router)
    dp.include_router(profile.router)
    dp.include_router(propose.router)
    dp.include_router(referral.router)
    dp.include_router(chest.router)
    dp.include_router(active_tasks.router)
    dp.include_router(support.router)
    dp.include_router(panel.router)
    dp.include_router(admin_gw.router)
    dp.include_router(moderation.router)
    dp.include_router(channels.router)
    dp.include_router(gifts.router)
    dp.include_router(whitelist.router)
    dp.include_router(stats.router)
    dp.include_router(broadcast.router)

    return dp


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await init_db()

    bot = Bot(token=settings.bot_token)
    dp = await create_dispatcher()
    scheduler = setup_scheduler(bot)
    scheduler.start()

    from bot.services.users import ensure_admin_roles
    from bot.database import async_session

    async with async_session() as session:
        await ensure_admin_roles(session)
        from bot.services.users import get_feature_flag

        for flag in ("daily_chest", "leaderboard", "referral", "seasonal_events"):
            await get_feature_flag(session, flag, True)
        await session.commit()

    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
