from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def init_db() -> None:
    from bot.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if "sqlite" in settings.database_url:
            from sqlalchemy import text

            migrations = [
                "ALTER TABLE withdrawal_requests ADD COLUMN gift_id INTEGER",
                "ALTER TABLE participations ADD COLUMN is_winner BOOLEAN",
                "ALTER TABLE giveaways ADD COLUMN winner_participation_id INTEGER",
                "ALTER TABLE giveaways ADD COLUMN draw_completed BOOLEAN DEFAULT 0",
            ]
            for sql in migrations:
                try:
                    await conn.execute(text(sql))
                except Exception:
                    pass
