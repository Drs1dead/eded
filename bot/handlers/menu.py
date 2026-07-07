from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.database import async_session
from bot.keyboards.inline import main_menu_kb
from bot.services.users import is_staff

router = Router()


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return
    async with async_session() as session:
        admin = await is_staff(session, callback.from_user.id)
    await callback.message.edit_text("🏠 Главное меню", reply_markup=main_menu_kb(is_admin=admin))
    await callback.answer()
