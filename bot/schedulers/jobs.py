from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from bot.database import async_session
from bot.models import Participation, ParticipationStatus, SnoozeReminder
from bot.services.giveaways import close_expired_giveaways
from bot.services.withdrawals import get_overdue_withdrawals
from bot.config import settings
from bot.utils.helpers import utcnow


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    @scheduler.scheduled_job("interval", minutes=15)
    async def close_deadlines():
        async with async_session() as session:
            await close_expired_giveaways(session, bot)
            await session.commit()

    @scheduler.scheduled_job("interval", hours=1)
    async def snooze_reminders():
        now = utcnow()
        async with async_session() as session:
            result = await session.execute(
                select(SnoozeReminder).where(
                    SnoozeReminder.remind_at <= now,
                    SnoozeReminder.sent == False,
                )
            )
            for rem in result.scalars():
                from bot.models import User

                u = await session.get(User, rem.user_id)
                if u:
                    try:
                        await bot.send_message(u.telegram_id, "⏰ Напоминание: у вас есть незавершённое задание!")
                    except Exception:
                        pass
                rem.sent = True
            await session.commit()

    @scheduler.scheduled_job("interval", hours=6)
    async def withdrawal_sla():
        async with async_session() as session:
            overdue = await get_overdue_withdrawals(session, days=3)
            for w in overdue:
                for admin_id in settings.admin_id_list:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"⚠️ Просроченная заявка на вывод #{w.id} (>3 дней)",
                        )
                    except Exception:
                        pass

    @scheduler.scheduled_job("cron", hour=10)
    async def daily_task_reminder():
        async with async_session() as session:
            result = await session.execute(
                select(Participation).where(Participation.status == ParticipationStatus.in_progress)
            )
            seen = set()
            for p in result.scalars():
                if p.user_id in seen:
                    continue
                seen.add(p.user_id)
                from bot.models import User

                u = await session.get(User, p.user_id)
                if u:
                    try:
                        await bot.send_message(u.telegram_id, "📋 Напоминание: у вас есть незавершённые задания!")
                    except Exception:
                        pass

    return scheduler
