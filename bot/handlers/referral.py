from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import settings
from bot.database import async_session
from bot.keyboards.inline import back_to_menu_kb
from bot.services.referral import get_referral_link, get_referral_status
from bot.utils.helpers import format_user

router = Router()


@router.callback_query(F.data == "menu:referral")
async def referral_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return
    uid = callback.from_user.id
    bot_username = settings.bot_username or (await callback.bot.get_me()).username

    async with async_session() as session:
        status = await get_referral_status(session, uid)

    if not status["can_invite"]:
        referred = status.get("referred")
        name = format_user(referred)
        text = f"👥 Вы уже пригласили друга: {name}\n\nЛимит: 1 друг на аккаунт."
    else:
        link = await get_referral_link(bot_username, uid)
        text = (
            "👥 <b>Пригласите друга</b>\n\n"
            "Пригласите одного друга — он получит доступ без одобрения админа.\n"
            "Вы получите <b>5 ⭐</b> после его регистрации.\n\n"
            f"🔗 Ваша ссылка:\n<code>{link}</code>"
        )

    await callback.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()
