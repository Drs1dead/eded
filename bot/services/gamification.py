import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Participation, ParticipationStatus, StarTransaction, User
from bot.services.users import add_stars, get_feature_flag
from bot.utils.helpers import ensure_utc, level_from_tasks, utcnow


async def claim_daily_chest(session: AsyncSession, user: User) -> tuple[bool, int, str]:
    if not await get_feature_flag(session, "daily_chest", True):
        return False, 0, "Сундук временно недоступен."

    now = utcnow()
    last_claim = ensure_utc(user.last_chest_claim)
    if last_claim:
        next_claim = last_claim + timedelta(hours=24)
        if now < next_claim:
            remaining = next_claim - now
            hours = int(remaining.total_seconds() // 3600)
            mins = int((remaining.total_seconds() % 3600) // 60)
            return False, 0, f"Сундук будет доступен через {hours}ч {mins}мин."

    amount = random.randint(1, 5)
    user.last_chest_claim = now
    await add_stars(session, user, amount, "daily_chest", description="Ежедневный сундук")
    return True, amount, f"Вы получили {amount} ⭐!"


async def update_streak(session: AsyncSession, user: User) -> int:
    today = date.today()
    if user.last_streak_date == today:
        return user.streak_days
    if user.last_streak_date == today - timedelta(days=1):
        user.streak_days += 1
    else:
        user.streak_days = 1
    user.last_streak_date = today
    return user.streak_days


async def apply_task_reward(
    session: AsyncSession,
    user: User,
    base_stars: int,
    multiplier: float = 1.0,
    participation_id: int | None = None,
) -> int:
    streak = await update_streak(session, user)
    bonus_pct = 0.1 if streak >= 7 and streak % 7 == 0 else 0
    total = int(base_stars * multiplier * (1 + bonus_pct))
    user.approved_tasks_count += 1
    user.level = level_from_tasks(user.approved_tasks_count)
    await add_stars(
        session,
        user,
        total,
        "task_reward",
        reference_id=participation_id,
        description=f"Награда за задание (+{total} ⭐)",
    )
    return total


async def get_leaderboard(session: AsyncSession, limit: int = 10) -> list[tuple[int, int]]:
    month_ago = utcnow() - timedelta(days=30)
    subq = (
        select(
            StarTransaction.user_id,
            func.sum(StarTransaction.amount).label("month_stars"),
        )
        .where(
            StarTransaction.amount > 0,
            StarTransaction.created_at >= month_ago,
        )
        .group_by(StarTransaction.user_id)
        .order_by(func.sum(StarTransaction.amount).desc())
        .limit(limit)
    )
    result = await session.execute(subq)
    return [(row.user_id, row.month_stars) for row in result.all()]
