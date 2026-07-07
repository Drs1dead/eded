from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from datetime import datetime

from bot.database import async_session
from bot.keyboards.inline import back_to_menu_kb, confirm_kb, giveaway_types_kb
from bot.models import Channel, Giveaway, GiveawayStatus, GiveawayType, User
from bot.services.giveaways import (
    close_giveaway,
    count_eligible_participants,
    count_participants,
    create_giveaway,
    list_admin_active_giveaways,
    publish_to_channels,
    run_randomizer_draw,
)
from bot.services.users import get_user_by_telegram_id, is_staff
from bot.states.forms import AdminCreateGiveawayStates
from bot.utils.helpers import ensure_utc, format_user, GIVEAWAY_TYPE_LABELS
from sqlalchemy import select

router = Router()


@router.callback_query(F.data == "admin:active_gw")
async def admin_active_giveaways(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    async with async_session() as session:
        if not await is_staff(session, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        giveaways = await list_admin_active_giveaways(session)
        if not giveaways:
            await callback.message.edit_text(
                "Нет активных розыгрышей.",
                reply_markup=back_to_menu_kb(),
            )
            await callback.answer()
            return

        text = "⏹ <b>Активные розыгрыши</b>\n\n"
        rows = []
        for gw in giveaways[:15]:
            type_label = GIVEAWAY_TYPE_LABELS.get(gw.giveaway_type.value, gw.giveaway_type.value)
            participants = await count_participants(session, gw.id)
            extra = ""
            if gw.giveaway_type == GiveawayType.randomizer:
                eligible = await count_eligible_participants(session, gw.id)
                extra = f", к розыгрышу: {eligible}"
            deadline = (
                f"\n   ⏰ {gw.deadline.strftime('%d.%m.%Y %H:%M')}" if gw.deadline else "\n   ⏰ без дедлайна"
            )
            text += f"• <b>{gw.title}</b> ({type_label})\n   👥 {participants}{extra}{deadline}\n"
            row = [
                InlineKeyboardButton(text=f"⏹ Завершить #{gw.id}", callback_data=f"admin:gw_close:{gw.id}"),
            ]
            if gw.giveaway_type == GiveawayType.randomizer and not gw.draw_completed:
                row.append(
                    InlineKeyboardButton(text="🎲 Розыгрыш", callback_data=f"admin:gw_draw:{gw.id}")
                )
            rows.append(row)
        rows.append([InlineKeyboardButton(text="🔙 Админ-панель", callback_data="admin:panel")])
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:gw_close:"))
async def admin_close_giveaway(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    gw_id = int(callback.data.split(":")[-1])
    async with async_session() as session:
        if not await is_staff(session, callback.from_user.id):
            return
        gw = await close_giveaway(session, gw_id, callback.bot)
        if not gw:
            await callback.answer("Розыгрыш не найден или уже завершён", show_alert=True)
            return
        await session.commit()
    await callback.answer("Розыгрыш завершён")
    await admin_active_giveaways(callback)


@router.callback_query(F.data.startswith("admin:gw_draw:"))
async def admin_run_draw(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    gw_id = int(callback.data.split(":")[-1])
    async with async_session() as session:
        if not await is_staff(session, callback.from_user.id):
            return
        gw = await session.get(Giveaway, gw_id)
        if not gw or gw.giveaway_type != GiveawayType.randomizer:
            await callback.answer("Не рандомайзер", show_alert=True)
            return
        if gw.draw_completed:
            await callback.answer("Розыгрыш уже проведён", show_alert=True)
            return
        winner = await run_randomizer_draw(session, gw, callback.bot)
        await session.commit()
        if winner:
            user = await session.get(User, winner.user_id)
            await callback.answer(f"Победитель: {format_user(user)}")
        else:
            await callback.answer("Нет участников для розыгрыша", show_alert=True)
            return
    await admin_active_giveaways(callback)


@router.callback_query(F.data == "admin:create_gw")
async def admin_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        return
    async with async_session() as session:
        if not await is_staff(session, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
    await state.set_state(AdminCreateGiveawayStates.choose_type)
    rows = giveaway_types_kb("adm_gw_type").inline_keyboard
    rows.insert(0, [InlineKeyboardButton(text="📋 Черновики", callback_data="admin:drafts")])
    await callback.message.edit_text(
        "Создание розыгрыша — выберите тип:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:drafts")
async def admin_drafts(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        result = await session.execute(
            select(Giveaway).where(
                Giveaway.author_id == user.id,
                Giveaway.status == GiveawayStatus.draft,
            )
        )
        drafts = list(result.scalars().all())
        if not drafts:
            await callback.answer("Нет черновиков", show_alert=True)
            return
        rows = [
            [InlineKeyboardButton(text=d.title or f"Черновик #{d.id}", callback_data=f"admin:draft:{d.id}")]
            for d in drafts
        ]
        rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin:create_gw")])
        await callback.message.edit_text("📋 Черновики:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:draft:"))
async def open_draft(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or not callback.from_user:
        return
    draft_id = int(callback.data.split(":")[-1])
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        gw = await session.get(Giveaway, draft_id)
        if not gw or not user or gw.author_id != user.id or gw.status != GiveawayStatus.draft:
            await callback.answer("Черновик не найден", show_alert=True)
            return
        await state.update_data(
            giveaway_type=gw.giveaway_type.value,
            title=gw.title,
            description=gw.description,
            media=gw.media,
            deadline=gw.deadline.isoformat() if gw.deadline else None,
            draft_id=gw.id,
            selected_channels=[],
        )
        channels = list((await session.execute(select(Channel))).scalars().all())
        if not channels:
            await state.set_state(AdminCreateGiveawayStates.confirm)
            await callback.message.edit_text(
                f"📋 Черновик: <b>{gw.title}</b>\n\nКаналы не добавлены. Опубликовать?",
                reply_markup=confirm_kb("adm_gw:publish", "admin:drafts"),
                parse_mode="HTML",
            )
            await callback.answer()
            return
        rows = [
            [InlineKeyboardButton(text=f"☐ {c.title or c.username}", callback_data=f"adm_ch:toggle:{c.id}")]
            for c in channels
        ]
        rows.append([InlineKeyboardButton(text="✅ Готово", callback_data="adm_ch:done")])
        await state.set_state(AdminCreateGiveawayStates.select_channels)
        await callback.message.edit_text(
            f"📋 Черновик: <b>{gw.title}</b>\n\nВыберите каналы для публикации:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(AdminCreateGiveawayStates.choose_type, F.data.startswith("adm_gw_type:"))
async def admin_choose_type(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await state.update_data(giveaway_type=callback.data.split(":")[-1])
    await state.set_state(AdminCreateGiveawayStates.enter_title)
    await callback.message.edit_text("Введите название:")
    await callback.answer()


@router.message(AdminCreateGiveawayStates.enter_title)
async def admin_enter_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text)
    await state.set_state(AdminCreateGiveawayStates.enter_content)
    await message.answer("Введите описание:")


@router.message(AdminCreateGiveawayStates.enter_content)
async def admin_enter_content(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text)
    data = await state.get_data()
    if data.get("giveaway_type") in ("photo", "complex"):
        await state.set_state(AdminCreateGiveawayStates.enter_media)
        await message.answer("Отправьте медиа (фото/видео) или /skip:")
        return
    await state.set_state(AdminCreateGiveawayStates.enter_deadline)
    await message.answer("Введите дедлайн (ДД.ММ.ГГГГ ЧЧ:ММ) или /skip:")


@router.message(AdminCreateGiveawayStates.enter_media)
async def admin_enter_media(message: Message, state: FSMContext) -> None:
    media = None
    if message.photo:
        media = {"type": "photo", "file_id": message.photo[-1].file_id}
    elif message.video:
        media = {"type": "video", "file_id": message.video.file_id}
    elif message.text and message.text.strip() == "/skip":
        pass
    await state.update_data(media=media)
    await state.set_state(AdminCreateGiveawayStates.enter_deadline)
    await message.answer("Введите дедлайн (ДД.ММ.ГГГГ ЧЧ:ММ) или /skip:")


@router.message(AdminCreateGiveawayStates.enter_deadline)
async def admin_enter_deadline(message: Message, state: FSMContext) -> None:
    deadline = None
    if message.text and message.text.strip() != "/skip":
        try:
            deadline = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        except ValueError:
            await message.answer("Неверный формат. Попробуйте снова или /skip:")
            return
    await state.update_data(deadline=deadline.isoformat() if deadline else None)
    await state.set_state(AdminCreateGiveawayStates.select_channels)

    async with async_session() as session:
        channels = await session.execute(select(Channel))
        ch_list = list(channels.scalars().all())
        if not ch_list:
            await state.update_data(selected_channels=[])
            await state.set_state(AdminCreateGiveawayStates.confirm)
            await message.answer(
                "Каналы не добавлены. Опубликовать без каналов?",
                reply_markup=confirm_kb("adm_gw:publish", "admin:panel"),
            )
            return
        rows = [
            [InlineKeyboardButton(text=f"☐ {c.title or c.username}", callback_data=f"adm_ch:toggle:{c.id}")]
            for c in ch_list
        ]
        rows.append([InlineKeyboardButton(text="✅ Готово", callback_data="adm_ch:done")])
        await state.update_data(selected_channels=[])
        await message.answer("Выберите каналы:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(AdminCreateGiveawayStates.select_channels, F.data.startswith("adm_ch:toggle:"))
async def admin_toggle_channel(callback: CallbackQuery, state: FSMContext) -> None:
    ch_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    selected = data.get("selected_channels", [])
    if ch_id in selected:
        selected.remove(ch_id)
    else:
        selected.append(ch_id)
    await state.update_data(selected_channels=selected)
    await callback.answer(f"Выбрано: {len(selected)}")


@router.callback_query(AdminCreateGiveawayStates.select_channels, F.data == "adm_ch:done")
async def admin_channels_done(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await state.set_state(AdminCreateGiveawayStates.confirm)
    await callback.message.edit_text(
        "📤 Опубликовать розыгрыш?",
        reply_markup=confirm_kb("adm_gw:publish", "admin:panel"),
    )
    await callback.answer()


@router.callback_query(F.data == "adm_gw:publish")
async def admin_publish(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not callback.from_user or not callback.message:
        return
    data = await state.get_data()
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        deadline = None
        if data.get("deadline"):
            deadline = ensure_utc(datetime.fromisoformat(data["deadline"]))

        draft_id = data.get("draft_id")
        if draft_id:
            gw = await session.get(Giveaway, draft_id)
            if gw:
                gw.title = data.get("title", gw.title)
                gw.description = data.get("description", gw.description)
                gw.media = data.get("media", gw.media)
                gw.deadline = deadline
                gw.status = GiveawayStatus.active
        else:
            gw = await create_giveaway(
                session,
                GiveawayType(data["giveaway_type"]),
                data.get("title", ""),
                data.get("description", ""),
                author_id=user.id,
                media=data.get("media"),
                deadline=deadline,
                status=GiveawayStatus.active,
            )
        selected = data.get("selected_channels", [])
        if selected:
            await publish_to_channels(session, gw.id, selected)

        await session.commit()

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📝 Принять это задание", callback_data=f"task:accept:{gw.id}")]
            ]
        )
        post_text = f"🎁 <b>{gw.title}</b>\n\n{gw.description}"

        for ch_id in selected:
            ch = await session.get(Channel, ch_id)
            if ch:
                try:
                    if gw.media and gw.media.get("type") == "photo":
                        await bot.send_photo(ch.chat_id, gw.media["file_id"], caption=post_text, reply_markup=kb, parse_mode="HTML")
                    else:
                        await bot.send_message(ch.chat_id, post_text, reply_markup=kb, parse_mode="HTML")
                except Exception:
                    pass

    await state.clear()
    await callback.message.edit_text("✅ Розыгрыш опубликован!", reply_markup=back_to_menu_kb())
    await callback.answer()
