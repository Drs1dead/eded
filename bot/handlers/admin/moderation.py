from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database import async_session
from bot.keyboards.inline import moderation_actions_kb
from bot.models import (
    Channel,
    Giveaway,
    GiveawayProposal,
    GiveawayStatus,
    GiveawayType,
    Idea,
    ModerationStatus,
    User,
)
from bot.services.giveaways import create_giveaway, publish_to_channels
from bot.services.users import is_staff
from bot.services.withdrawals import block_content_hash, log_moderation
from bot.states.forms import AdminReworkStates
from bot.utils.helpers import format_user
from sqlalchemy import select

router = Router()


@router.callback_query(F.data == "admin:mod_gw")
async def mod_giveaways_list(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    async with async_session() as session:
        if not await is_staff(session, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        result = await session.execute(
            select(GiveawayProposal).where(GiveawayProposal.status == ModerationStatus.pending)
        )
        proposals = list(result.scalars().all())
        if not proposals:
            await callback.message.edit_text("📭 Нет заявок на модерацию.")
            await callback.answer()
            return
        for p in proposals[:5]:
            author = await session.get(User, p.author_id)
            text = (
                f"📌 <b>{p.title}</b>\n"
                f"Автор: {format_user(author)}\n"
                f"Тип: {p.giveaway_type.value}\n"
                f"{p.description[:300]}"
            )
            await callback.message.answer(text, reply_markup=moderation_actions_kb("gwprop", p.id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin:mod_ideas")
async def mod_ideas_list(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    async with async_session() as session:
        if not await is_staff(session, callback.from_user.id):
            return
        result = await session.execute(select(Idea).where(Idea.status == ModerationStatus.pending))
        ideas = list(result.scalars().all())
        if not ideas:
            await callback.message.edit_text("📭 Нет идей на модерацию.")
            await callback.answer()
            return
        for idea in ideas[:5]:
            author = await session.get(User, idea.author_id)
            text = f"💡 Идея от {format_user(author)}:\n{idea.text[:500]}"
            await callback.message.answer(text, reply_markup=moderation_actions_kb("idea", idea.id))
    await callback.answer()


@router.callback_query(F.data.startswith("mod:gwprop:approve:"))
async def approve_proposal(callback: CallbackQuery, state: FSMContext) -> None:
    prop_id = int(callback.data.split(":")[-1])
    await state.update_data(mod_entity="gwprop", mod_id=prop_id, mod_action="approve")
    async with async_session() as session:
        channels = await session.execute(select(Channel))
        ch_list = list(channels.scalars().all())
        rows = [
            [InlineKeyboardButton(text=f"☐ {c.title}", callback_data=f"mod_ch:toggle:{c.id}")]
            for c in ch_list
        ]
        rows.append([InlineKeyboardButton(text="✅ Опубликовать", callback_data="mod_ch:publish")])
        await state.update_data(mod_channels=[])
        await callback.message.answer("Выберите каналы:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data.startswith("mod_ch:toggle:"))
async def mod_toggle_channel(callback: CallbackQuery, state: FSMContext) -> None:
    ch_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    selected = data.get("mod_channels", [])
    if ch_id in selected:
        selected.remove(ch_id)
    else:
        selected.append(ch_id)
    await state.update_data(mod_channels=selected)
    await callback.answer()


@router.callback_query(F.data == "mod_ch:publish")
async def mod_publish_proposal(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not callback.from_user:
        return
    data = await state.get_data()
    prop_id = data.get("mod_id")
    async with async_session() as session:
        prop = await session.get(GiveawayProposal, prop_id)
        if not prop:
            return
        author = await session.get(User, prop.author_id)
        gw = await create_giveaway(
            session,
            prop.giveaway_type,
            prop.title,
            prop.description,
            author_id=prop.author_id,
            media=prop.media,
            status=GiveawayStatus.active,
        )
        selected = data.get("mod_channels", [])
        if selected:
            await publish_to_channels(session, gw.id, selected)
        old_status = prop.status.value
        prop.status = ModerationStatus.approved
        await log_moderation(session, "giveaway_proposal", prop.id, callback.from_user.id, old_status, "approved")
        await session.commit()

        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="📝 Принять задание", callback_data=f"task:accept:{gw.id}")]]
        )
        for ch_id in selected:
            ch = await session.get(Channel, ch_id)
            if ch:
                try:
                    await bot.send_message(ch.chat_id, f"🎁 {gw.title}\n\n{gw.description}", reply_markup=kb)
                except Exception:
                    pass
        if author:
            try:
                await bot.send_message(author.telegram_id, "✅ Ваш розыгрыш одобрен и опубликован!")
            except Exception:
                pass
    await callback.answer("Опубликовано")


@router.callback_query(F.data.regexp(r"^mod:(?:gwprop|idea):rework:\d+$"))
async def mod_rework(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    entity, entity_id = parts[1], int(parts[3])
    await state.update_data(mod_entity=entity, mod_id=entity_id)
    await state.set_state(AdminReworkStates.enter_comment)
    await callback.message.answer("Введите комментарий для пользователя:")
    await callback.answer()


@router.message(AdminReworkStates.enter_comment)
async def mod_rework_comment(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    data = await state.get_data()
    entity, entity_id = data.get("mod_entity"), data.get("mod_id")
    async with async_session() as session:
        if entity == "gwprop":
            obj = await session.get(GiveawayProposal, entity_id)
        else:
            obj = await session.get(Idea, entity_id)
        if not obj:
            return
        old_status = obj.status.value
        obj.status = ModerationStatus.rework
        obj.comment = message.text
        await log_moderation(session, entity, entity_id, message.from_user.id, old_status, "rework", message.text)
        author = await session.get(User, obj.author_id)
        await session.commit()
        if author:
            try:
                await message.bot.send_message(
                    author.telegram_id,
                    f"✏️ Требуется доработка:\n{message.text}\n\nОтправьте исправленную версию.",
                )
            except Exception:
                pass
    await state.clear()
    await message.answer("Комментарий отправлен.")


@router.callback_query(F.data.regexp(r"^mod:(?:gwprop|idea):reject:\d+$"))
async def mod_reject(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return
    parts = callback.data.split(":")
    entity, entity_id = parts[1], int(parts[3])
    async with async_session() as session:
        if entity == "gwprop":
            obj = await session.get(GiveawayProposal, entity_id)
        else:
            obj = await session.get(Idea, entity_id)
        if not obj:
            return
        old_status = obj.status.value
        obj.status = ModerationStatus.rejected_permanently
        await block_content_hash(session, obj.content_hash, entity, "rejected")
        await log_moderation(session, entity, entity_id, callback.from_user.id, old_status, "rejected_permanently")
        author = await session.get(User, obj.author_id)
        await session.commit()
        if author:
            try:
                await callback.bot.send_message(author.telegram_id, "❌ Ваша заявка отклонена.")
            except Exception:
                pass
    await callback.answer("Отклонено")
