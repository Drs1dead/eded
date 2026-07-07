from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database import async_session
from bot.keyboards.inline import back_to_menu_kb
from bot.models import Gift, GiftDesign, GiftType, StarTransaction
from bot.services.gamification import get_leaderboard
from bot.services.users import get_user_by_telegram_id
from bot.services.withdrawals import create_withdrawal, notify_managers
from bot.states.forms import WithdrawStarsStates
from bot.utils.helpers import LEVEL_NAMES, format_user
from sqlalchemy import select

router = Router()

MIN_WITHDRAW_STARS = 15


def _available(user) -> int:
    return user.star_balance - user.reserved_stars


@router.callback_query(F.data == "menu:profile")
async def profile_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return

        available = _available(user)
        level_name = LEVEL_NAMES.get(user.level, "Новичок")
        text = (
            f"👤 <b>Профиль</b>\n\n"
            f"⭐ Баланс: <b>{available}</b>"
            + (f" (зарезервировано: {user.reserved_stars})" if user.reserved_stars else "")
            + f"\n🏅 Уровень: {level_name} (Lv.{user.level})\n"
            f"🔥 Стрик: {user.streak_days} дн.\n"
            f"✅ Выполнено заданий: {user.approved_tasks_count}\n\n"
            f"Вы можете вывести звёзды с баланса:\n"
            f"• <b>Звёздами</b> — анонимный подарок (15–49) или на аккаунт (50+)\n"
            f"• <b>Подарком</b> — приз из каталога за звёзды"
        )

        rows = []
        if available >= MIN_WITHDRAW_STARS:
            rows.append([InlineKeyboardButton(text="⭐ Вывести звёздами", callback_data="profile:wd_stars")])
            rows.append([InlineKeyboardButton(text="🎁 Вывести подарком", callback_data="profile:wd_catalog")])
        rows.append([InlineKeyboardButton(text="📜 История транзакций", callback_data="profile:tx")])
        rows.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="menu:main")])

        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "profile:tx")
async def profile_transactions(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        if not user:
            return
        result = await session.execute(
            select(StarTransaction)
            .where(StarTransaction.user_id == user.id)
            .order_by(StarTransaction.created_at.desc())
            .limit(15)
        )
        txs = list(result.scalars().all())
        text = "📜 <b>История транзакций</b>\n\n"
        for tx in txs:
            sign = "+" if tx.amount > 0 else ""
            text += f"{sign}{tx.amount} ⭐ — {tx.description or tx.tx_type}\n"
        if not txs:
            text += "Пусто."
        await callback.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "profile:wd_stars")
async def withdraw_stars_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or not callback.from_user:
        return
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        available = _available(user) if user else 0
    if available < MIN_WITHDRAW_STARS:
        await callback.answer(f"Минимум {MIN_WITHDRAW_STARS} ⭐", show_alert=True)
        return
    await state.set_state(WithdrawStarsStates.enter_amount)
    await callback.message.edit_text(
        f"⭐ <b>Вывод звёздами</b>\n\n"
        f"Доступно: {available} ⭐\n"
        f"Минимум: {MIN_WITHDRAW_STARS} ⭐\n\n"
        f"Введите сумму для вывода:",
        reply_markup=back_to_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(WithdrawStarsStates.enter_amount)
async def withdraw_stars_amount(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer("Введите число:")
        return

    async with async_session() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        available = _available(user)
        if amount < MIN_WITHDRAW_STARS:
            await message.answer(f"Минимальная сумма — {MIN_WITHDRAW_STARS} ⭐")
            return
        if amount > available:
            await message.answer(f"Недостаточно звёзд. Доступно: {available} ⭐")
            return

        if 15 <= amount < 50:
            designs = list(
                (await session.execute(select(GiftDesign).where(GiftDesign.is_active.is_(True)))).scalars().all()
            )
            if designs:
                await state.update_data(wd_amount=amount, wd_mode="stars")
                rows = [
                    [InlineKeyboardButton(text=d.name, callback_data=f"profile:wd_design:{amount}:{d.id}")]
                    for d in designs
                ]
                rows.append([InlineKeyboardButton(text="🔙 Профиль", callback_data="menu:profile")])
                await message.answer(
                    "🎨 Выберите оформление анонимного подарка:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                )
                return

        wr = await create_withdrawal(session, user, amount)
        if not wr:
            await message.answer("Не удалось создать заявку.")
            await state.clear()
            return
        await session.commit()
        if amount >= 50:
            await notify_managers(
                message.bot,
                session,
                f"💰 Вывод {amount} ⭐ на аккаунт\nПользователь: {format_user(user)}",
            )

    await state.clear()
    await message.answer(
        "✅ Заявка на вывод звёзд отправлена.\nС вами свяжется менеджер в течение 3 дней.",
        reply_markup=back_to_menu_kb(),
    )


@router.callback_query(F.data.startswith("profile:wd_design:"))
async def withdraw_stars_with_design(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        return
    parts = callback.data.split(":")
    amount, design_id = int(parts[2]), int(parts[3])
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        wr = await create_withdrawal(session, user, amount, gift_design_id=design_id)
        if not wr:
            await callback.answer("Недостаточно звёзд", show_alert=True)
            return
        await session.commit()
    await state.clear()
    await callback.message.edit_text(
        "✅ Заявка на вывод звёзд отправлена.\nС вами свяжется менеджер в течение 3 дней.",
        reply_markup=back_to_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:wd_catalog")
async def withdraw_catalog(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        available = _available(user) if user else 0
        gifts = list(
            (
                await session.execute(
                    select(Gift).where(Gift.is_active.is_(True)).order_by(Gift.star_cost.asc())
                )
            ).scalars().all()
        )
        affordable = [g for g in gifts if g.star_cost <= available]
        if not affordable:
            await callback.message.edit_text(
                "🎁 Нет доступных подарков за ваш баланс.\n"
                f"Баланс: {available} ⭐\n\n"
                "Админ может добавить подарки в каталог.",
                reply_markup=back_to_menu_kb(),
            )
            await callback.answer()
            return
        rows = [
            [InlineKeyboardButton(text=f"{g.name} — {g.star_cost} ⭐", callback_data=f"profile:wd_gift:{g.id}")]
            for g in affordable
        ]
        rows.append([InlineKeyboardButton(text="🔙 Профиль", callback_data="menu:profile")])
        await callback.message.edit_text(
            f"🎁 <b>Каталог подарков</b>\n\nБаланс: {available} ⭐\nВыберите подарок:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("profile:wd_gift:"))
async def withdraw_catalog_gift(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        return
    gift_id = int(callback.data.split(":")[-1])
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        gift = await session.get(Gift, gift_id)
        if not gift or not user:
            await callback.answer("Не найдено", show_alert=True)
            return
        if gift.star_cost > _available(user):
            await callback.answer("Недостаточно звёзд", show_alert=True)
            return

        if gift.gift_type == GiftType.gift and 15 <= gift.star_cost < 50:
            designs = list(
                (await session.execute(select(GiftDesign).where(GiftDesign.is_active.is_(True)))).scalars().all()
            )
            if designs:
                rows = [
                    [
                        InlineKeyboardButton(
                            text=d.name,
                            callback_data=f"profile:wd_gift_design:{gift_id}:{d.id}",
                        )
                    ]
                    for d in designs
                ]
                rows.append([InlineKeyboardButton(text="🔙 Профиль", callback_data="menu:profile")])
                await callback.message.edit_text(
                    f"🎨 Оформление для «{gift.name}»:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                )
                await callback.answer()
                return

        wr = await create_withdrawal(session, user, gift.star_cost, gift_id=gift.id)
        if not wr:
            await callback.answer("Недостаточно звёзд", show_alert=True)
            return
        await session.commit()
        if gift.star_cost >= 50 or gift.gift_type == GiftType.account:
            await notify_managers(
                callback.bot,
                session,
                f"💰 Вывод подарка «{gift.name}» ({gift.star_cost} ⭐)\nПользователь: {format_user(user)}",
            )

    await callback.message.edit_text(
        f"✅ Заявка на подарок «{gift.name}» отправлена.\nС вами свяжется менеджер в течение 3 дней.",
        reply_markup=back_to_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("profile:wd_gift_design:"))
async def withdraw_gift_with_design(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return
    parts = callback.data.split(":")
    gift_id, design_id = int(parts[2]), int(parts[3])
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        gift = await session.get(Gift, gift_id)
        if not gift or not user:
            return
        wr = await create_withdrawal(
            session, user, gift.star_cost, gift_id=gift.id, gift_design_id=design_id
        )
        if not wr:
            await callback.answer("Недостаточно звёзд", show_alert=True)
            return
        await session.commit()
    await callback.message.edit_text(
        f"✅ Заявка на подарок «{gift.name}» отправлена.\nС вами свяжется менеджер в течение 3 дней.",
        reply_markup=back_to_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:leaderboard")
async def leaderboard(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    async with async_session() as session:
        from bot.services.users import get_feature_flag

        if not await get_feature_flag(session, "leaderboard", True):
            await callback.message.edit_text("Лидерборд временно недоступен.", reply_markup=back_to_menu_kb())
            await callback.answer()
            return
        board = await get_leaderboard(session)
        text = "🏆 <b>Топ-10 за месяц</b> (анонимно)\n\n"
        for i, (_, stars) in enumerate(board, 1):
            text += f"{i}. Участник — {stars} ⭐\n"
        if not board:
            text += "Пока пусто."
        await callback.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()
