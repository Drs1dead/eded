from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database import async_session
from bot.services.users import (
    add_whitelist_from_input,
    is_staff,
    list_pending_whitelist,
    list_whitelist,
    remove_from_whitelist,
    remove_pending_whitelist,
)
from bot.states.forms import AdminWhitelistStates
from bot.utils.helpers import format_user

router = Router()


@router.callback_query(F.data == "admin:whitelist")
async def whitelist_menu(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    async with async_session() as session:
        if not await is_staff(session, callback.from_user.id):
            return
        users = await list_whitelist(session)
        pending = await list_pending_whitelist(session)
        text = f"👥 <b>Whitelist</b> ({len(users)})\n\n"
        if users:
            for u in users:
                text += f"• {format_user(u)}\n"
        else:
            text += "Пусто.\n"
        if pending:
            text += f"\n⏳ <b>Ожидают /start</b> ({len(pending)}):\n"
            for p in pending:
                text += f"• @{p.username}\n"

        rows = []
        for u in users[:15]:
            label = format_user(u)[:24]
            rows.append([
                InlineKeyboardButton(text=label, callback_data="noop"),
                InlineKeyboardButton(text="✖️", callback_data=f"admin:wl_del:{u.telegram_id}"),
            ])
        for p in pending[:10]:
            rows.append([
                InlineKeyboardButton(text=f"⏳ @{p.username}", callback_data="noop"),
                InlineKeyboardButton(text="✖️", callback_data=f"admin:wl_pend_del:{p.username}"),
            ])
        rows.append([InlineKeyboardButton(text="➕ Добавить", callback_data="admin:wl_add")])
        rows.append([InlineKeyboardButton(text="🔙 Админ-панель", callback_data="admin:panel")])
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "admin:wl_add")
async def wl_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await state.set_state(AdminWhitelistStates.enter_user_id)
    await callback.message.edit_text(
        "Введите @username или Telegram ID:\n\n"
        "Примеры:\n"
        "• @username\n"
        "• username\n"
        "• 123456789"
    )
    await callback.answer()


@router.message(AdminWhitelistStates.enter_user_id)
async def wl_add_user(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    async with async_session() as session:
        result = await add_whitelist_from_input(session, message.text, added_by=message.from_user.id)
        await session.commit()
    await state.clear()
    await message.answer(result)


@router.callback_query(F.data.startswith("admin:wl_del:"))
async def wl_delete(callback: CallbackQuery) -> None:
    uid = int(callback.data.split(":")[-1])
    async with async_session() as session:
        await remove_from_whitelist(session, uid)
        await session.commit()
    await callback.answer("Удалено")
    await whitelist_menu(callback)


@router.callback_query(F.data.startswith("admin:wl_pend_del:"))
async def wl_pending_delete(callback: CallbackQuery) -> None:
    username = callback.data.split(":", 2)[-1]
    async with async_session() as session:
        await remove_pending_whitelist(session, username)
        await session.commit()
    await callback.answer("Удалено")
    await whitelist_menu(callback)
