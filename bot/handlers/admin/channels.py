from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.enums import ChatMemberStatus

from bot.database import async_session
from bot.models import Channel
from bot.services.users import is_staff
from bot.states.forms import AdminAddChannelStates
from bot.utils.channel_parser import parse_channel_input
from sqlalchemy import select

router = Router()


@router.callback_query(F.data == "admin:channels")
async def channels_list(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    async with async_session() as session:
        if not await is_staff(session, callback.from_user.id):
            return
        result = await session.execute(select(Channel))
        channels = list(result.scalars().all())
        rows = []
        for ch in channels:
            rows.append([
                InlineKeyboardButton(text=f"📣 {ch.title or ch.username}", callback_data="noop"),
                InlineKeyboardButton(text="✖️", callback_data=f"admin:ch_del:{ch.id}"),
            ])
        rows.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin:ch_add")])
        rows.append([InlineKeyboardButton(text="🔙 Админ-панель", callback_data="admin:panel")])
        text = "📣 Каналы:\n" + ("\n".join(f"• {c.title} (@{c.username})" for c in channels) if channels else "Пусто")
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data == "admin:ch_add")
async def channel_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await state.set_state(AdminAddChannelStates.enter_username)
    await callback.message.edit_text(
        "Введите канал в одном из форматов:\n\n"
        "• @username\n"
        "• https://t.me/username\n"
        "• https://t.me/c/1234567890 (приватный канал)\n"
        "• -1001234567890 (chat_id)\n\n"
        "⚠️ Бот должен быть администратором канала."
    )
    await callback.answer()


@router.message(AdminAddChannelStates.enter_username)
async def channel_add_username(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.text:
        return
    parsed = parse_channel_input(message.text)
    try:
        if isinstance(parsed, int):
            chat = await bot.get_chat(parsed)
        else:
            chat = await bot.get_chat(f"@{parsed}")

        member = await bot.get_chat_member(chat.id, bot.id)
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            await message.answer(
                "❌ Бот не является администратором канала.\n"
                "Добавьте бота в канал как админа с правом публикации сообщений."
            )
            await state.clear()
            return

        username = chat.username or str(chat.id)
        async with async_session() as session:
            existing = await session.execute(select(Channel).where(Channel.chat_id == chat.id))
            if existing.scalar_one_or_none():
                await message.answer("Канал уже добавлен.")
            else:
                session.add(Channel(chat_id=chat.id, username=username, title=chat.title))
                await session.commit()
                label = f"@{chat.username}" if chat.username else str(chat.id)
                await message.answer(f"✅ Канал {label} добавлен.")
    except Exception as e:
        await message.answer(
            f"❌ Не удалось найти канал: {e}\n\n"
            "Проверьте:\n"
            "1. Бот добавлен в канал как администратор\n"
            "2. Ссылка или @username указаны верно\n"
            "3. Для приватного канала используйте ссылку t.me/c/..."
        )
    await state.clear()


@router.callback_query(F.data.startswith("admin:ch_del:"))
async def channel_delete(callback: CallbackQuery) -> None:
    ch_id = int(callback.data.split(":")[-1])
    async with async_session() as session:
        ch = await session.get(Channel, ch_id)
        if ch:
            await session.delete(ch)
            await session.commit()
    await callback.answer("Удалено")
    await channels_list(callback)


@router.callback_query(F.data.startswith("task:accept:"))
async def accept_task_from_channel(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return
    gw_id = int(callback.data.split(":")[-1])
    from bot.services.users import is_whitelisted, get_user_by_telegram_id
    from bot.services.giveaways import get_giveaway, is_giveaway_open, start_participation
    from bot.handlers.giveaways_helpers import send_giveaway_detail

    async with async_session() as session:
        if not await is_whitelisted(session, callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        gw = await get_giveaway(session, gw_id)
        if not gw or not user:
            await callback.answer("Розыгрыш не найден", show_alert=True)
            return
        if not await is_giveaway_open(gw):
            await callback.answer("Розыгрыш уже завершён", show_alert=True)
            return
        await start_participation(session, user.id, gw)
        await session.commit()
        try:
            await callback.bot.send_message(
                callback.from_user.id,
                f"🎁 Задание: {gw.title}\n\n{gw.description}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Начать выполнение", callback_data=f"gw:join:{gw.id}")]
                    ]
                ),
            )
        except Exception:
            pass
    await callback.answer("Задание отправлено в личные сообщения")
