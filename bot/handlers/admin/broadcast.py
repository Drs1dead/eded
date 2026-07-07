from datetime import timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database import async_session
from bot.keyboards.inline import confirm_kb
from bot.models import BroadcastLog
from bot.services.users import is_staff, list_whitelist
from bot.states.forms import AdminBroadcastStates
from bot.utils.helpers import utcnow

router = Router()


@router.callback_query(F.data == "admin:broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or not callback.from_user:
        return
    async with async_session() as session:
        if not await is_staff(session, callback.from_user.id):
            return
        day_ago = utcnow() - timedelta(days=1)
        from sqlalchemy import select

        recent = await session.execute(
            select(BroadcastLog).where(
                BroadcastLog.admin_id == callback.from_user.id,
                BroadcastLog.created_at >= day_ago,
            )
        )
        if recent.scalar_one_or_none():
            await callback.answer("Рассылка уже была сегодня (лимит 1/день)", show_alert=True)
            return
    await state.set_state(AdminBroadcastStates.enter_message)
    await callback.message.edit_text("📣 Введите текст рассылки для whitelist:")
    await callback.answer()


@router.message(AdminBroadcastStates.enter_message)
async def broadcast_message(message: Message, state: FSMContext) -> None:
    await state.update_data(broadcast_text=message.text)
    await state.set_state(AdminBroadcastStates.confirm)
    await message.answer(
        f"Подтвердите рассылку:\n\n{message.text}",
        reply_markup=confirm_kb("admin:broadcast_send", "admin:panel"),
    )


@router.callback_query(F.data == "admin:broadcast_send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not callback.from_user or not callback.message:
        return
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    sent = 0
    async with async_session() as session:
        users = await list_whitelist(session)
        for u in users:
            try:
                await bot.send_message(u.telegram_id, f"📣 {text}")
                sent += 1
            except Exception:
                pass
        session.add(BroadcastLog(admin_id=callback.from_user.id, message=text, sent_count=sent))
        await session.commit()
    await state.clear()
    await callback.message.edit_text(f"✅ Рассылка отправлена ({sent} пользователей).")
    await callback.answer()


@router.callback_query(F.data == "admin:health")
async def health_check(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.message:
        return
    from aiogram.enums import ChatMemberStatus
    from bot.models import Channel
    from sqlalchemy import select

    async with async_session() as session:
        channels = list((await session.execute(select(Channel))).scalars().all())
        text = "🔧 Health-check каналов:\n\n"
        for ch in channels:
            try:
                member = await bot.get_chat_member(ch.chat_id, bot.id)
                ok = member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
                text += f"{'✅' if ok else '❌'} {ch.title or ch.username}\n"
            except Exception as e:
                text += f"❌ {ch.title}: {e}\n"
        if not channels:
            text += "Каналы не добавлены."
        await callback.message.edit_text(text)
    await callback.answer()
