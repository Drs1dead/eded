from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.database import async_session
from bot.handlers.giveaways_helpers import send_giveaway_detail
from bot.keyboards.inline import main_menu_kb
from bot.services.giveaways import get_giveaway, is_giveaway_open, start_participation
from bot.services.referral import ReferralError, process_referral
from bot.services.users import (
    apply_pending_whitelist,
    ensure_admin_roles,
    get_or_create_user,
    get_user_by_telegram_id,
    is_staff,
    is_whitelisted,
)
router = Router()


async def show_main_menu(message: Message, telegram_id: int) -> None:
    async with async_session() as session:
        admin = await is_staff(session, telegram_id)
    await message.answer("🏠 Главное меню", reply_markup=main_menu_kb(is_admin=admin))


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id
    args = message.text.split(maxsplit=1)[1] if message.text and " " in message.text else ""

    async with async_session() as session:
        await ensure_admin_roles(session)
        user = await get_or_create_user(session, uid, message.from_user.username, message.from_user.first_name)
        await apply_pending_whitelist(session, user)

        if args.startswith("ref_"):
            try:
                referrer_id = int(args.removeprefix("ref_"))
                referral, referrer = await process_referral(
                    session,
                    uid,
                    referrer_id,
                    message.from_user.username,
                    message.from_user.first_name,
                )
                await session.commit()
                await message.answer("✅ Добро пожаловать! Вы получили доступ по приглашению.")
                try:
                    await message.bot.send_message(
                        referrer.telegram_id,
                        f"🎉 Ваш друг присоединился! Вам начислено {referral.stars_awarded} ⭐",
                    )
                except Exception:
                    pass
                await show_main_menu(message, uid)
                return
            except ReferralError as e:
                await session.rollback()
                await message.answer(str(e))
                return
            except Exception:
                await session.rollback()
                await message.answer("Ошибка обработки реферальной ссылки.")
                return

        if args.startswith("task_"):
            try:
                gw_id = int(args.removeprefix("task_"))
                if not await is_whitelisted(session, uid):
                    await message.answer("⛔ Доступ запрещён.")
                    return
                gw = await get_giveaway(session, gw_id)
                if not gw:
                    await message.answer("Розыгрыш не найден.")
                    return
                if not await is_giveaway_open(gw):
                    await message.answer("⏹ Этот розыгрыш уже завершён.")
                    return
                user = await get_user_by_telegram_id(session, uid)
                if user:
                    await start_participation(session, user.id, gw)
                    await session.commit()
                    await send_giveaway_detail(message, gw, user.id, session)
                    return
            except ValueError:
                pass

        if await is_whitelisted(session, uid):
            await session.commit()
            await show_main_menu(message, uid)
            return

        await session.commit()
    await message.answer("⛔ Доступ запрещён.")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📖 Справка\n\n"
        "• /start — главное меню\n"
        "• Розыгрыши — участие в заданиях\n"
        "• Профиль — баланс и вывод подарков\n"
        "• Пригласить друга — 1 друг, +5 ⭐\n"
        "• Сундук — 1–5 ⭐ раз в сутки"
    )
