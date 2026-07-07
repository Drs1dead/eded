from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import AccessType, Referral
from bot.services.users import (
    add_stars,
    add_to_whitelist,
    get_or_create_user,
    get_referral_by_referred,
    get_referral_by_referrer,
    get_user_by_telegram_id,
    is_whitelisted,
)
from bot.utils.helpers import format_user

REFERRAL_BONUS = 5


class ReferralError(Exception):
    pass


async def process_referral(
    session: AsyncSession,
    referred_telegram_id: int,
    referrer_telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> tuple[Referral, object]:
    if referred_telegram_id == referrer_telegram_id:
        raise ReferralError("Нельзя использовать свою ссылку.")

    if await is_whitelisted(session, referred_telegram_id):
        raise ReferralError("У вас уже есть доступ.")

    referrer = await get_user_by_telegram_id(session, referrer_telegram_id)
    if not referrer or not await is_whitelisted(session, referrer_telegram_id):
        raise ReferralError("Ссылка недействительна.")

    if await get_referral_by_referrer(session, referrer.id):
        raise ReferralError("По этой ссылке уже пригласили максимум друзей.")

    referred = await get_or_create_user(session, referred_telegram_id, username, first_name)
    if await get_referral_by_referred(session, referred.id):
        raise ReferralError("Вы уже были приглашены ранее.")

    await add_to_whitelist(session, referred_telegram_id, added_by=referrer_telegram_id, access_type=AccessType.referral)

    referral = Referral(referrer_id=referrer.id, referred_id=referred.id, stars_awarded=REFERRAL_BONUS)
    session.add(referral)
    await add_stars(
        session,
        referrer,
        REFERRAL_BONUS,
        "referral_bonus",
        description=f"Приглашение друга {format_user(referred)}",
    )
    await session.flush()
    return referral, referrer


async def get_referral_link(bot_username: str, telegram_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref_{telegram_id}"


async def get_referral_status(session: AsyncSession, telegram_id: int) -> dict:
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        return {"can_invite": True, "referral": None}
    referral = await get_referral_by_referrer(session, user.id)
    if referral:
        referred = await session.get(type(user), referral.referred_id) if False else None
        from bot.models import User

        referred_result = await session.execute(select(User).where(User.id == referral.referred_id))
        referred = referred_result.scalar_one_or_none()
        return {
            "can_invite": False,
            "referral": referral,
            "referred": referred,
        }
    return {"can_invite": True, "referral": None}
