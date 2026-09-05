from datetime import datetime, timezone
import random

from aiogram import Bot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.models import (
    Channel,
    Giveaway,
    GiveawayChannel,
    GiveawayStatus,
    GiveawayType,
    Participation,
    ParticipationStatus,
    TaskStep,
    User,
)
from bot.utils.helpers import content_hash, gives_instant_reward, utcnow


async def create_giveaway(
    session: AsyncSession,
    giveaway_type: GiveawayType,
    title: str,
    description: str,
    author_id: int | None = None,
    media: dict | None = None,
    deadline: datetime | None = None,
    star_reward: int = 10,
    star_multiplier: float = 1.0,
    status: GiveawayStatus = GiveawayStatus.draft,
    steps: list[dict] | None = None,
) -> Giveaway:
    text_for_hash = f"{title}{description}{giveaway_type.value}"
    gw = Giveaway(
        giveaway_type=giveaway_type,
        title=title,
        description=description,
        author_id=author_id,
        media=media,
        deadline=deadline,
        star_reward=star_reward,
        star_multiplier=star_multiplier,
        status=status,
        content_hash=content_hash(text_for_hash),
    )
    session.add(gw)
    await session.flush()
    if steps:
        for i, step in enumerate(steps):
            session.add(
                TaskStep(
                    giveaway_id=gw.id,
                    step_order=i + 1,
                    description=step.get("description", ""),
                    requires_photo=step.get("requires_photo", False),
                )
            )
    return gw


async def is_giveaway_open(gw: Giveaway) -> bool:
    if gw.status != GiveawayStatus.active:
        return False
    if gw.deadline and gw.deadline < utcnow():
        return False
    return True


async def list_admin_active_giveaways(session: AsyncSession) -> list[Giveaway]:
    result = await session.execute(
        select(Giveaway)
        .where(Giveaway.status == GiveawayStatus.active)
        .order_by(Giveaway.created_at.desc())
    )
    return list(result.scalars().all())


async def count_eligible_participants(session: AsyncSession, giveaway_id: int) -> int:
    result = await session.execute(
        select(func.count()).where(
            Participation.giveaway_id == giveaway_id,
            Participation.status == ParticipationStatus.approved,
            Participation.is_winner.is_(None),
        )
    )
    return result.scalar() or 0


async def list_giveaway_participants(
    session: AsyncSession,
    giveaway_id: int,
    *,
    approved_only: bool = False,
) -> list[tuple[Participation, User]]:
    """Return participants together with their user profiles."""
    query = (
        select(Participation, User)
        .join(User, User.id == Participation.user_id)
        .where(Participation.giveaway_id == giveaway_id)
        .order_by(Participation.created_at.asc())
    )
    if approved_only:
        query = query.where(Participation.status == ParticipationStatus.approved)
    result = await session.execute(query)
    return [(participation, user) for participation, user in result.all()]


async def list_active_giveaways(session: AsyncSession, page: int = 0, per_page: int = 5) -> tuple[list[Giveaway], int]:
    now = utcnow()
    q = (
        select(Giveaway)
        .where(
            Giveaway.status == GiveawayStatus.active,
            (Giveaway.deadline.is_(None)) | (Giveaway.deadline > now),
        )
        .order_by(Giveaway.created_at.desc())
    )
    count_result = await session.execute(select(func.count()).select_from(q.subquery()))
    total = count_result.scalar() or 0
    result = await session.execute(q.offset(page * per_page).limit(per_page))
    return list(result.scalars().all()), total


async def get_giveaway(session: AsyncSession, giveaway_id: int) -> Giveaway | None:
    result = await session.execute(
        select(Giveaway)
        .options(selectinload(Giveaway.steps), selectinload(Giveaway.channels))
        .where(Giveaway.id == giveaway_id)
    )
    return result.scalar_one_or_none()


async def get_participation(
    session: AsyncSession, user_id: int, giveaway_id: int
) -> Participation | None:
    result = await session.execute(
        select(Participation).where(
            Participation.user_id == user_id,
            Participation.giveaway_id == giveaway_id,
        )
    )
    return result.scalar_one_or_none()


async def start_participation(session: AsyncSession, user_id: int, giveaway: Giveaway) -> Participation:
    existing = await get_participation(session, user_id, giveaway.id)
    if existing:
        return existing
    p = Participation(user_id=user_id, giveaway_id=giveaway.id)
    session.add(p)
    await session.flush()
    return p


async def list_user_active_participations(session: AsyncSession, user_id: int) -> list[Participation]:
    result = await session.execute(
        select(Participation)
        .options(selectinload(Participation))
        .where(
            Participation.user_id == user_id,
            Participation.status.in_([ParticipationStatus.in_progress, ParticipationStatus.on_review]),
        )
        .order_by(Participation.created_at.desc())
    )
    return list(result.scalars().all())


async def submit_answer(
    session: AsyncSession,
    participation: Participation,
    answer_text: str | None = None,
    answer_media: dict | None = None,
) -> None:
    participation.answer_text = answer_text
    participation.answer_media = answer_media
    participation.status = ParticipationStatus.on_review
    participation.submitted_at = utcnow()


async def run_randomizer_draw(
    session: AsyncSession,
    gw: Giveaway,
    bot: Bot | None = None,
) -> Participation | None:
    if gw.draw_completed or gw.giveaway_type != GiveawayType.randomizer:
        return None

    result = await session.execute(
        select(Participation).where(
            Participation.giveaway_id == gw.id,
            Participation.status == ParticipationStatus.approved,
            Participation.is_winner.is_(None),
        )
    )
    eligible = list(result.scalars().all())
    gw.draw_completed = True

    if not eligible:
        return None

    winner = random.choice(eligible)
    winner.is_winner = True
    gw.winner_participation_id = winner.id

    from bot.services.gamification import apply_task_reward

    winner_user = await session.get(User, winner.user_id)
    stars = 0
    if winner_user:
        stars = await apply_task_reward(
            session, winner_user, gw.star_reward, gw.star_multiplier, winner.id
        )

    for p in eligible:
        if p.id == winner.id:
            continue
        p.is_winner = False
        if bot:
            user = await session.get(User, p.user_id)
            if user:
                try:
                    await bot.send_message(
                        user.telegram_id,
                        f"🎲 Розыгрыш «{gw.title}» завершён. К сожалению, в этот раз не повезло.",
                    )
                except Exception:
                    pass

    if bot and winner_user:
        try:
            await bot.send_message(
                winner_user.telegram_id,
                f"🏆 Поздравляем! Вы выиграли в розыгрыше «{gw.title}»! +{stars} ⭐",
            )
        except Exception:
            pass

    return winner


async def close_giveaway(
    session: AsyncSession,
    giveaway_id: int,
    bot: Bot | None = None,
) -> Giveaway | None:
    gw = await get_giveaway(session, giveaway_id)
    if not gw or gw.status != GiveawayStatus.active:
        return None

    gw.status = GiveawayStatus.closed

    if bot:
        result = await session.execute(
            select(Participation).where(
                Participation.giveaway_id == gw.id,
                Participation.status == ParticipationStatus.in_progress,
            )
        )
        for p in result.scalars():
            user = await session.get(User, p.user_id)
            if user:
                try:
                    await bot.send_message(
                        user.telegram_id,
                        f"⏹ Розыгрыш «{gw.title}» завершён.",
                    )
                except Exception:
                    pass

    if gw.giveaway_type == GiveawayType.randomizer:
        await run_randomizer_draw(session, gw, bot)

    return gw


async def close_expired_giveaways(session: AsyncSession, bot: Bot | None = None) -> list[Giveaway]:
    now = utcnow()
    result = await session.execute(
        select(Giveaway).where(
            Giveaway.status == GiveawayStatus.active,
            Giveaway.deadline.isnot(None),
            Giveaway.deadline < now,
        )
    )
    giveaways = list(result.scalars().all())
    closed: list[Giveaway] = []
    for gw in giveaways:
        closed_gw = await close_giveaway(session, gw.id, bot)
        if closed_gw:
            closed.append(closed_gw)
    return closed


async def publish_to_channels(session: AsyncSession, giveaway_id: int, channel_ids: list[int]) -> None:
    for cid in channel_ids:
        session.add(GiveawayChannel(giveaway_id=giveaway_id, channel_id=cid))


async def count_participants(session: AsyncSession, giveaway_id: int) -> int:
    result = await session.execute(
        select(func.count()).where(Participation.giveaway_id == giveaway_id)
    )
    return result.scalar() or 0


async def list_draft_giveaways(session: AsyncSession, author_id: int) -> list[Giveaway]:
    result = await session.execute(
        select(Giveaway).where(
            Giveaway.author_id == author_id,
            Giveaway.status == GiveawayStatus.draft,
        )
    )
    return list(result.scalars().all())
