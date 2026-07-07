from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database import async_session
from bot.handlers.admin.panel import get_admin_counts
from bot.models import (
    Giveaway,
    GiveawayStatus,
    GiveawayType,
    Gift,
    GiftDesign,
    Idea,
    ModerationStatus,
    Participation,
    StarTransaction,
    User,
    UserGift,
    WithdrawalRequest,
)
from bot.services.gamification import apply_task_reward
from bot.services.users import count_whitelist, get_user_by_telegram_id, is_staff, resolve_user_input
from bot.utils.helpers import format_user, GIVEAWAY_TYPE_LABELS
from bot.services.withdrawals import complete_withdrawal, list_pending_withdrawals
from bot.states.forms import AdminSearchUserStates
from bot.utils.helpers import LEVEL_NAMES
from sqlalchemy import func, select

router = Router()


@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    async with async_session() as session:
        if not await is_staff(session, callback.from_user.id):
            return
        wl_count = await count_whitelist(session)
        active_gw = await session.execute(
            select(func.count()).where(Giveaway.status == GiveawayStatus.active)
        )
        pending_w = list(await list_pending_withdrawals(session))
        counts = await get_admin_counts(session)
        text = (
            f"📊 <b>Статистика</b>\n\n"
            f"👥 Пользователей в whitelist: {wl_count}\n"
            f"🎁 Активных розыгрышей: {active_gw.scalar() or 0}\n"
            f"📤 Заявок на вывод (pending): {len(pending_w)}\n"
            f"📌 Модерация розыгрышей: {counts['proposals']}\n"
            f"💡 Модерация идей: {counts['ideas']}\n"
        )
        rows = [
            [InlineKeyboardButton(text="🔍 Поиск пользователя", callback_data="admin:search_user")],
            [InlineKeyboardButton(text=f"📤 Заявки на вывод ({len(pending_w)})", callback_data="admin:withdrawals")],
            [InlineKeyboardButton(text="✅ Проверка заданий", callback_data="admin:review_tasks")],
            [InlineKeyboardButton(text="🔙 Админ-панель", callback_data="admin:panel")],
        ]
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin:search_user")
async def search_user_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await state.set_state(AdminSearchUserStates.enter_user_id)
    await callback.message.edit_text("Введите @username или Telegram ID:")
    await callback.answer()


@router.message(AdminSearchUserStates.enter_user_id)
async def search_user_result(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    async with async_session() as session:
        user = await resolve_user_input(session, message.text)
        if not user:
            await message.answer("Пользователь не найден. Укажите @username или ID.")
            await state.clear()
            return
        parts = list(
            (await session.execute(select(Participation).where(Participation.user_id == user.id))).scalars().all()
        )
        gifts = list(
            (await session.execute(select(UserGift).where(UserGift.user_id == user.id))).scalars().all()
        )
        ideas = list(
            (await session.execute(select(Idea).where(Idea.author_id == user.id))).scalars().all()
        )
        withdrawals = list(
            (await session.execute(select(WithdrawalRequest).where(WithdrawalRequest.user_id == user.id))).scalars().all()
        )
        level = LEVEL_NAMES.get(user.level, "?")
        text = (
            f"🔍 <b>Досье</b>\n\n"
            f"Пользователь: {format_user(user)}\n"
            f"Регистрация: {user.registered_at.strftime('%d.%m.%Y')}\n"
            f"⭐ Баланс: {user.star_balance} (резерв: {user.reserved_stars})\n"
            f"🏅 {level}\n\n"
            f"📋 Заданий: {len(parts)}\n"
            f"🎁 Подарков: {len(gifts)}\n"
            f"💡 Идей: {len(ideas)}\n"
            f"📤 Выводов: {len(withdrawals)}"
        )
        await message.answer(text, parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "admin:withdrawals")
async def withdrawals_list(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    async with async_session() as session:
        pending = await list_pending_withdrawals(session)
        if not pending:
            await callback.message.edit_text("Нет pending заявок.")
            await callback.answer()
            return
        for w in pending[:10]:
            user = await session.get(User, w.user_id)
            gift = await session.get(Gift, w.gift_id) if w.gift_id else None
            design = await session.get(GiftDesign, w.gift_design_id) if w.gift_design_id else None
            kind = "⭐ Звёзды"
            if gift:
                kind = f"🎁 {gift.name}"
            if design:
                kind += f" ({design.name})"
            rows = [[InlineKeyboardButton(text="✅ Выдано", callback_data=f"admin:wd_done:{w.id}")]]
            await callback.message.answer(
                f"📤 Вывод #{w.id}\n"
                f"Пользователь: {format_user(user)}\n"
                f"Тип: {kind}\n"
                f"⭐ {w.stars_amount}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:wd_done:"))
async def withdrawal_done(callback: CallbackQuery) -> None:
    wid = int(callback.data.split(":")[-1])
    async with async_session() as session:
        wr = await complete_withdrawal(session, wid)
        if wr:
            user = await session.get(User, wr.user_id)
            await session.commit()
            if user:
                try:
                    await callback.bot.send_message(user.telegram_id, "✅ Ваш вывод выполнен!")
                except Exception:
                    pass
    await callback.answer("Выполнено")


@router.callback_query(F.data == "admin:review_tasks")
async def review_tasks(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    from bot.models import ParticipationStatus

    async with async_session() as session:
        result = await session.execute(
            select(Participation).where(Participation.status == ParticipationStatus.on_review)
        )
        parts = list(result.scalars().all())
        if not parts:
            await callback.message.edit_text("Нет заявок на проверку.")
            await callback.answer()
            return
        for p in parts[:10]:
            user = await session.get(User, p.user_id)
            gw = await session.get(Giveaway, p.giveaway_id)
            rows = [
                [
                    InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin:part_ok:{p.id}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:part_no:{p.id}"),
                ]
            ]
            ans = p.answer_text or "(медиа)"
            gw_type = GIVEAWAY_TYPE_LABELS.get(gw.giveaway_type.value, gw.giveaway_type.value) if gw else "?"
            await callback.message.answer(
                f"📝 {gw.title if gw else '?'}\n"
                f"Тип: {gw_type}\n"
                f"Пользователь: {format_user(user)}\n"
                f"{ans[:200]}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:part_ok:"))
async def approve_participation(callback: CallbackQuery) -> None:
    pid = int(callback.data.split(":")[-1])
    from bot.models import ParticipationStatus

    async with async_session() as session:
        p = await session.get(Participation, pid)
        if not p:
            await callback.answer("Не найдено", show_alert=True)
            return
        user = await session.get(User, p.user_id)
        gw = await session.get(Giveaway, p.giveaway_id)
        if not user or not gw:
            await callback.answer("Данные не найдены", show_alert=True)
            return
        p.status = ParticipationStatus.approved
        if gw.giveaway_type == GiveawayType.randomizer:
            p.is_winner = None
            await session.commit()
            try:
                await callback.bot.send_message(
                    user.telegram_id,
                    f"✅ Заявка принята в розыгрыш «{gw.title}»!\nОжидайте определения победителя.",
                )
            except Exception:
                pass
            await callback.answer("Допущен к розыгрышу")
            return

        stars = await apply_task_reward(
            session, user, gw.star_reward, gw.star_multiplier, p.id
        )
        await session.commit()
        try:
            await callback.bot.send_message(user.telegram_id, f"✅ Задание одобрено! +{stars} ⭐")
        except Exception:
            pass
    await callback.answer("Одобрено")


@router.callback_query(F.data.startswith("admin:part_no:"))
async def reject_participation(callback: CallbackQuery) -> None:
    pid = int(callback.data.split(":")[-1])
    from bot.models import ParticipationStatus

    async with async_session() as session:
        p = await session.get(Participation, pid)
        if p:
            p.status = ParticipationStatus.rejected
            user = await session.get(User, p.user_id)
            await session.commit()
            if user:
                try:
                    await callback.bot.send_message(user.telegram_id, "❌ Задание отклонено.")
                except Exception:
                    pass
    await callback.answer("Отклонено")
