from datetime import datetime, timedelta, timezone

from bot.utils.helpers import utcnow

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import (
    ContentHash,
    Gift,
    GiftDesign,
    GiftType,
    ModerationLog,
    ModerationStatus,
    UserGift,
    UserGiftStatus,
    WithdrawalRequest,
    WithdrawalStatus,
)
from bot.services.users import deduct_stars, get_staff_role, release_reserved_stars, reserve_stars
from bot.models import StaffRole


async def create_withdrawal(
    session: AsyncSession,
    user,
    stars_amount: int,
    user_gift_id: int | None = None,
    gift_id: int | None = None,
    gift_design_id: int | None = None,
) -> WithdrawalRequest | None:
    if not await reserve_stars(session, user, stars_amount):
        return None
    wr = WithdrawalRequest(
        user_id=user.id,
        user_gift_id=user_gift_id,
        gift_id=gift_id,
        gift_design_id=gift_design_id,
        stars_amount=stars_amount,
    )
    session.add(wr)
    if user_gift_id:
        gift = await session.get(UserGift, user_gift_id)
        if gift:
            gift.status = UserGiftStatus.withdrawn
    await session.flush()
    return wr


async def notify_managers(bot, session: AsyncSession, message: str) -> None:
    from bot.config import settings
    from bot.models import StaffRole, StaffRoleEntry

    managers = await session.execute(
        select(StaffRoleEntry).where(StaffRoleEntry.role.in_([StaffRole.manager, StaffRole.admin]))
    )
    from bot.models import User

    for m in managers.scalars():
        mgr = await session.get(User, m.user_id)
        if mgr:
            try:
                await bot.send_message(mgr.telegram_id, message)
            except Exception:
                pass
    for admin_id in settings.admin_id_list:
        try:
            await bot.send_message(admin_id, message)
        except Exception:
            pass


async def complete_withdrawal(session: AsyncSession, withdrawal_id: int) -> WithdrawalRequest | None:
    wr = await session.get(WithdrawalRequest, withdrawal_id)
    if not wr or wr.status != WithdrawalStatus.pending:
        return None
    from bot.models import User

    user = await session.get(User, wr.user_id)
    if user:
        await deduct_stars(
            session,
            user,
            wr.stars_amount,
            "withdrawal",
            reference_id=wr.id,
            description="Вывод подарка",
            from_reserved=True,
        )
    wr.status = WithdrawalStatus.completed
    wr.completed_at = utcnow()
    return wr


async def log_moderation(
    session: AsyncSession,
    entity_type: str,
    entity_id: int,
    admin_id: int,
    old_status: str | None,
    new_status: str,
    comment: str | None = None,
) -> None:
    session.add(
        ModerationLog(
            entity_type=entity_type,
            entity_id=entity_id,
            admin_id=admin_id,
            old_status=old_status,
            new_status=new_status,
            comment=comment,
        )
    )


async def block_content_hash(session: AsyncSession, hash_value: str, entity_type: str, reason: str) -> None:
    existing = await session.execute(select(ContentHash).where(ContentHash.content_hash == hash_value))
    if not existing.scalar_one_or_none():
        session.add(ContentHash(content_hash=hash_value, entity_type=entity_type, reason=reason))


async def is_content_blocked(session: AsyncSession, hash_value: str) -> bool:
    result = await session.execute(select(ContentHash).where(ContentHash.content_hash == hash_value))
    return result.scalar_one_or_none() is not None


async def count_pending_withdrawals(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count()).where(WithdrawalRequest.status == WithdrawalStatus.pending)
    )
    return result.scalar() or 0


async def list_pending_withdrawals(session: AsyncSession) -> list[WithdrawalRequest]:
    result = await session.execute(
        select(WithdrawalRequest)
        .where(WithdrawalRequest.status == WithdrawalStatus.pending)
        .order_by(WithdrawalRequest.created_at.asc())
    )
    return list(result.scalars().all())


async def get_overdue_withdrawals(session: AsyncSession, days: int = 3) -> list[WithdrawalRequest]:
    cutoff = utcnow() - timedelta(days=days)
    result = await session.execute(
        select(WithdrawalRequest).where(
            WithdrawalRequest.status == WithdrawalStatus.pending,
            WithdrawalRequest.created_at < cutoff,
        )
    )
    return list(result.scalars().all())
