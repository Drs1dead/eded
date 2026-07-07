from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database import async_session
from bot.keyboards.inline import back_to_menu_kb
from bot.services.gamification import claim_daily_chest
from bot.services.users import get_user_by_telegram_id

router = Router()


@router.callback_query(F.data == "menu:chest")
async def daily_chest(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        if not user:
            return
        ok, amount, msg = await claim_daily_chest(session, user)
        await session.commit()
    emoji = "🎉" if ok else "⏳"
    await callback.message.edit_text(f"{emoji} {msg}", reply_markup=back_to_menu_kb())
    await callback.answer()
