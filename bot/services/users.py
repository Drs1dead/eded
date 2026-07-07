from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.models import (
    AccessType,
    FeatureFlag,
    PendingWhitelist,
    Referral,
    StaffRole,
    StaffRoleEntry,
    StarTransaction,
    User,
    WhitelistEntry,
)
from bot.utils.helpers import format_user, normalize_username


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        if username and user.username != username:
            user.username = username
        if first_name and user.first_name != first_name:
            user.first_name = first_name
        return user
    user = User(telegram_id=telegram_id, username=username, first_name=first_name)
    session.add(user)
    await session.flush()
    return user


async def is_whitelisted(session: AsyncSession, telegram_id: int) -> bool:
    result = await session.execute(
        select(WhitelistEntry)
        .join(User)
        .where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none() is not None


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    uname = normalize_username(username)
    if not uname:
        return None
    result = await session.execute(
        select(User).where(func.lower(User.username) == uname)
    )
    return result.scalar_one_or_none()


async def resolve_user_input(session: AsyncSession, text: str) -> User | None:
    text = text.strip()
    if text.lstrip("-").isdigit():
        return await get_user_by_telegram_id(session, int(text))
    return await get_user_by_username(session, text)


async def add_pending_whitelist(session: AsyncSession, username: str, added_by: int | None = None) -> PendingWhitelist:
    uname = normalize_username(username)
    existing = await session.execute(select(PendingWhitelist).where(PendingWhitelist.username == uname))
    entry = existing.scalar_one_or_none()
    if entry:
        return entry
    entry = PendingWhitelist(username=uname, added_by=added_by)
    session.add(entry)
    await session.flush()
    return entry


async def list_pending_whitelist(session: AsyncSession) -> list[PendingWhitelist]:
    result = await session.execute(select(PendingWhitelist).order_by(PendingWhitelist.created_at.desc()))
    return list(result.scalars().all())


async def remove_pending_whitelist(session: AsyncSession, username: str) -> bool:
    uname = normalize_username(username)
    result = await session.execute(select(PendingWhitelist).where(PendingWhitelist.username == uname))
    entry = result.scalar_one_or_none()
    if entry:
        await session.delete(entry)
        return True
    return False


async def apply_pending_whitelist(session: AsyncSession, user: User) -> bool:
    if not user.username:
        return False
    uname = normalize_username(user.username)
    result = await session.execute(select(PendingWhitelist).where(PendingWhitelist.username == uname))
    entry = result.scalar_one_or_none()
    if not entry:
        return False
    await add_to_whitelist(session, user.telegram_id, added_by=entry.added_by)
    await session.delete(entry)
    return True


async def add_whitelist_from_input(session: AsyncSession, text: str, added_by: int | None = None) -> str:
    text = text.strip()
    if text.lstrip("-").isdigit():
        user = await add_to_whitelist(session, int(text), added_by=added_by)
        return f"✅ {format_user(user)} добавлен в whitelist."

    username = normalize_username(text)
    if not username:
        return "❌ Укажите @username или ID."

    existing_user = await get_user_by_username(session, username)
    if existing_user:
        user = await add_to_whitelist(session, existing_user.telegram_id, added_by=added_by)
        return f"✅ {format_user(user)} добавлен в whitelist."

    await add_pending_whitelist(session, username, added_by=added_by)
    return (
        f"✅ @{username} добавлен в ожидание.\n"
        "Доступ откроется, когда пользователь нажмёт /start в боте."
    )


async def remove_whitelist_from_input(session: AsyncSession, text: str) -> str:
    text = text.strip()
    if text.lstrip("-").isdigit():
        ok = await remove_from_whitelist(session, int(text))
        return "✅ Удалён из whitelist." if ok else "❌ Пользователь не найден."

    username = normalize_username(text)
    user = await get_user_by_username(session, username)
    if user and await remove_from_whitelist(session, user.telegram_id):
        return f"✅ @{username} удалён из whitelist."
    if await remove_pending_whitelist(session, username):
        return f"✅ @{username} удалён из ожидания."
    return "❌ Пользователь не найден."


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def add_to_whitelist(
    session: AsyncSession,
    telegram_id: int,
    added_by: int | None = None,
    access_type: AccessType = AccessType.whitelist,
) -> User:
    user = await get_or_create_user(session, telegram_id)
    user.access_type = access_type
    existing = await session.execute(select(WhitelistEntry).where(WhitelistEntry.user_id == user.id))
    if not existing.scalar_one_or_none():
        session.add(WhitelistEntry(user_id=user.id, added_by=added_by))
    return user


async def remove_from_whitelist(session: AsyncSession, telegram_id: int) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        return False
    result = await session.execute(select(WhitelistEntry).where(WhitelistEntry.user_id == user.id))
    entry = result.scalar_one_or_none()
    if entry:
        await session.delete(entry)
        user.access_type = None
        return True
    return False


async def list_whitelist(session: AsyncSession) -> list[User]:
    result = await session.execute(
        select(User).join(WhitelistEntry).order_by(User.registered_at.desc())
    )
    return list(result.scalars().all())


async def is_staff(session: AsyncSession, telegram_id: int, roles: list[StaffRole] | None = None) -> bool:
    from bot.config import settings

    if telegram_id in settings.admin_id_list:
        return True
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        return False
    result = await session.execute(select(StaffRoleEntry).where(StaffRoleEntry.user_id == user.id))
    entry = result.scalar_one_or_none()
    if not entry:
        return False
    if roles is None:
        return True
    return entry.role in roles


async def get_staff_role(session: AsyncSession, telegram_id: int) -> StaffRole | None:
    from bot.config import settings

    if telegram_id in settings.admin_id_list:
        return StaffRole.admin
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        return None
    result = await session.execute(select(StaffRoleEntry).where(StaffRoleEntry.user_id == user.id))
    entry = result.scalar_one_or_none()
    return entry.role if entry else None


async def ensure_admin_roles(session: AsyncSession) -> None:
    from bot.config import settings

    for admin_id in settings.admin_id_list:
        user = await get_or_create_user(session, admin_id)
        await add_to_whitelist(session, admin_id, access_type=AccessType.whitelist)
        result = await session.execute(select(StaffRoleEntry).where(StaffRoleEntry.user_id == user.id))
        if not result.scalar_one_or_none():
            session.add(StaffRoleEntry(user_id=user.id, role=StaffRole.admin))


async def add_stars(
    session: AsyncSession,
    user: User,
    amount: int,
    tx_type: str,
    reference_id: int | None = None,
    description: str | None = None,
) -> None:
    user.star_balance += amount
    session.add(
        StarTransaction(
            user_id=user.id,
            amount=amount,
            tx_type=tx_type,
            reference_id=reference_id,
            description=description,
        )
    )


async def reserve_stars(session: AsyncSession, user: User, amount: int) -> bool:
    available = user.star_balance - user.reserved_stars
    if available < amount:
        return False
    user.reserved_stars += amount
    return True


async def release_reserved_stars(session: AsyncSession, user: User, amount: int) -> None:
    user.reserved_stars = max(0, user.reserved_stars - amount)


async def deduct_stars(
    session: AsyncSession,
    user: User,
    amount: int,
    tx_type: str,
    reference_id: int | None = None,
    description: str | None = None,
    from_reserved: bool = False,
) -> bool:
    if from_reserved:
        if user.reserved_stars < amount:
            return False
        user.reserved_stars -= amount
    else:
        if user.star_balance - user.reserved_stars < amount:
            return False
    user.star_balance -= amount
    session.add(
        StarTransaction(
            user_id=user.id,
            amount=-amount,
            tx_type=tx_type,
            reference_id=reference_id,
            description=description,
        )
    )
    return True


async def get_feature_flag(session: AsyncSession, name: str, default: bool = True) -> bool:
    result = await session.execute(select(FeatureFlag).where(FeatureFlag.name == name))
    flag = result.scalar_one_or_none()
    if not flag:
        flag = FeatureFlag(name=name, enabled=default)
        session.add(flag)
        await session.flush()
    return flag.enabled


async def count_whitelist(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(WhitelistEntry))
    return result.scalar() or 0


async def get_referral_by_referrer(session: AsyncSession, referrer_user_id: int) -> Referral | None:
    result = await session.execute(select(Referral).where(Referral.referrer_id == referrer_user_id))
    return result.scalar_one_or_none()


async def get_referral_by_referred(session: AsyncSession, referred_user_id: int) -> Referral | None:
    result = await session.execute(select(Referral).where(Referral.referred_id == referred_user_id))
    return result.scalar_one_or_none()
