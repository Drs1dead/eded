from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database import async_session
from bot.keyboards.inline import back_to_menu_kb
from bot.models import SupportTicket
from bot.services.users import get_user_by_telegram_id, is_staff
from bot.states.forms import SupportStates
from bot.utils.helpers import format_user

router = Router()


@router.callback_query(F.data == "menu:support")
async def support_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await state.set_state(SupportStates.enter_message)
    await callback.message.edit_text("🆘 Опишите вашу проблему или вопрос:")
    await callback.answer()


@router.message(SupportStates.enter_message)
async def support_message(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        ticket = SupportTicket(user_id=user.id, message=message.text)
        session.add(ticket)
        await session.commit()

        from bot.config import settings
        for admin_id in settings.admin_id_list:
            try:
                await message.bot.send_message(
                    admin_id,
                    f"🆘 Тикет #{ticket.id} от {format_user(user)}:\n{message.text}",
                )
            except Exception:
                pass

    await state.clear()
    await message.answer(
        "✅ Обращение отправлено. Мы ответим в ближайшее время.",
        reply_markup=back_to_menu_kb(),
    )
