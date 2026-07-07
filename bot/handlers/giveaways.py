from datetime import timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message

from bot.database import async_session
from bot.handlers.giveaways_helpers import giveaway_card_text, send_giveaway_detail
from bot.keyboards.inline import back_to_menu_kb
from bot.models import GiveawayType, ParticipationStatus, StaffRole, SnoozeReminder
from bot.services.giveaways import (
    get_giveaway,
    get_participation,
    is_giveaway_open,
    list_active_giveaways,
    start_participation,
    submit_answer,
)
from bot.services.users import get_staff_role, get_user_by_telegram_id
from bot.utils.helpers import format_user
from bot.states.forms import TaskAnswerStates
from bot.utils.helpers import utcnow
from bot.utils.pagination import paginate

router = Router()


@router.callback_query(F.data == "menu:giveaways")
@router.callback_query(F.data.startswith("gw:list:page:"))
async def list_giveaways(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    page = 0
    if callback.data and callback.data.startswith("gw:list:page:"):
        page = int(callback.data.split(":")[-1])

    async with async_session() as session:
        items, total = await list_active_giveaways(session, page)

        if not items:
            await callback.message.edit_text("📭 Нет активных розыгрышей.", reply_markup=back_to_menu_kb())
            await callback.answer()
            return

        def render_btn(gw):
            return InlineKeyboardButton(
                text=f"🎁 {gw.title or 'Без названия'}",
                callback_data=f"gw:view:{gw.id}",
            )

        _, kb = paginate(items, page, 5, "gw:list", render_btn)
        text = f"🎁 Активные розыгрыши ({total}):"
        await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("gw:view:"))
async def view_giveaway(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    gw_id = int(callback.data.split(":")[-1])
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        gw = await get_giveaway(session, gw_id)
        if not gw or not user:
            await callback.answer("Не найдено", show_alert=True)
            return
        await callback.message.delete()
        await send_giveaway_detail(callback.message, gw, user.id, session)
    await callback.answer()


@router.callback_query(F.data.startswith("gw:answer:"))
async def continue_answer(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        return
    gw_id = int(callback.data.split(":")[-1])
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        gw = await get_giveaway(session, gw_id)
        part = await get_participation(session, user.id, gw_id) if user else None
        if not gw or not part or part.status != ParticipationStatus.in_progress:
            await callback.answer("Задание недоступно для ответа", show_alert=True)
            return
        if not await is_giveaway_open(gw):
            await callback.answer("Розыгрыш завершён", show_alert=True)
            return

        if gw.giveaway_type == GiveawayType.complex and gw.steps:
            step_idx = max(part.current_step, 0)
            step = gw.steps[step_idx] if step_idx < len(gw.steps) else gw.steps[0]
            await state.set_state(TaskAnswerStates.waiting_step)
            await state.update_data(gw_id=gw_id, participation_id=part.id, step=step_idx + 1)
            await callback.message.edit_text(
                f"🧩 Шаг {step_idx + 1}/{len(gw.steps)}: {step.description}",
                reply_markup=back_to_menu_kb(),
            )
            await callback.answer()
            return

        await state.set_state(TaskAnswerStates.waiting_answer)
        await state.update_data(gw_id=gw_id, participation_id=part.id)
        hint = "📤 Отправьте ваш ответ (текст или фото):"
        if gw.giveaway_type == GiveawayType.photo:
            hint = "📷 Отправьте фото:"
        await callback.message.edit_text(hint, reply_markup=back_to_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("gw:join:"))
async def join_giveaway(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        return
    gw_id = int(callback.data.split(":")[-1])
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        gw = await get_giveaway(session, gw_id)
        if not gw or not user:
            await callback.answer("Не найдено", show_alert=True)
            return
        if not await is_giveaway_open(gw):
            await callback.answer("Розыгрыш завершён", show_alert=True)
            return

        part = await start_participation(session, user.id, gw)

        if gw.giveaway_type == GiveawayType.manager:
            part.status = ParticipationStatus.on_review
            part.submitted_at = utcnow()
            role = await get_staff_role(session, callback.from_user.id)
            from sqlalchemy import select
            from bot.models import StaffRoleEntry

            managers = await session.execute(
                select(StaffRoleEntry).where(StaffRoleEntry.role.in_([StaffRole.manager, StaffRole.admin]))
            )
            for m in managers.scalars():
                mgr_user = await session.get(type(user), m.user_id)
                if mgr_user:
                    try:
                        await callback.bot.send_message(
                            mgr_user.telegram_id,
                            f"👔 Новая заявка «С обращением к менеджеру»\n"
                            f"Пользователь: {format_user(user)}\n"
                            f"Розыгрыш: {gw.title}",
                        )
                    except Exception:
                        pass
            await session.commit()
            await callback.message.edit_text(
                "⏳ Ожидайте, с вами свяжется менеджер.",
                reply_markup=back_to_menu_kb(),
            )
            await callback.answer()
            return

        if gw.giveaway_type == GiveawayType.complex and gw.steps:
            await session.commit()
            await state.set_state(TaskAnswerStates.waiting_step)
            await state.update_data(gw_id=gw_id, participation_id=part.id, step=1)
            step = gw.steps[0]
            await callback.message.edit_text(
                f"🧩 Шаг 1/{len(gw.steps)}: {step.description}",
                reply_markup=back_to_menu_kb(),
            )
            await callback.answer()
            return

        await session.commit()
        await state.set_state(TaskAnswerStates.waiting_answer)
        await state.update_data(gw_id=gw_id, participation_id=part.id)
        hint = "📤 Отправьте ваш ответ (текст или фото):"
        if gw.giveaway_type == GiveawayType.photo:
            hint = "📷 Отправьте фото:"
        await callback.message.edit_text(hint, reply_markup=back_to_menu_kb())
    await callback.answer()


@router.message(TaskAnswerStates.waiting_step)
async def receive_step_answer(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    gw_id = data.get("gw_id")
    step_num = data.get("step", 1)
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        gw = await get_giveaway(session, gw_id)
        part = await get_participation(session, user.id, gw_id) if user else None
        if not part or not gw:
            await state.clear()
            return
        if not await is_giveaway_open(gw):
            await state.clear()
            await message.answer("Розыгрыш уже завершён.", reply_markup=back_to_menu_kb())
            return
        answers = part.step_answers or {}
        key = f"step_{step_num}"
        if message.photo:
            answers[key] = {"type": "photo", "file_id": message.photo[-1].file_id}
        else:
            answers[key] = {"type": "text", "text": message.text}
        part.step_answers = answers
        part.current_step = step_num
        if step_num < len(gw.steps):
            next_step = gw.steps[step_num]
            await state.update_data(step=step_num + 1)
            await session.commit()
            await message.answer(f"🧩 Шаг {step_num + 1}/{len(gw.steps)}: {next_step.description}")
            return
        part.answer_text = str(answers)
        await submit_answer(session, part, part.answer_text, None)
        await session.commit()
        gw = await get_giveaway(session, gw_id)
    await state.clear()
    done_text = "✅ Все шаги выполнены! Заявка на проверке."
    if gw and gw.giveaway_type == GiveawayType.randomizer:
        done_text = (
            "✅ Все шаги выполнены!\n"
            "После одобрения админом вы будете участвовать в розыгрыше победителя."
        )
    await message.answer(done_text, reply_markup=back_to_menu_kb())


@router.message(TaskAnswerStates.waiting_answer)
async def receive_answer(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    gw_id = data.get("gw_id")
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        gw = await get_giveaway(session, gw_id)
        part = await get_participation(session, user.id, gw_id) if user else None
        if not part:
            await message.answer("Заявка не найдена.")
            await state.clear()
            return
        if gw and not await is_giveaway_open(gw):
            await state.clear()
            await message.answer("Розыгрыш уже завершён.", reply_markup=back_to_menu_kb())
            return

        answer_text = message.text or message.caption
        answer_media = None
        if message.photo:
            answer_media = {"type": "photo", "file_id": message.photo[-1].file_id}
        elif message.document:
            answer_media = {"type": "document", "file_id": message.document.file_id}

        await submit_answer(session, part, answer_text, answer_media)
        await session.commit()
        gw = await get_giveaway(session, gw_id)

    await state.clear()
    done_text = "✅ Ответ отправлен! Заявка на проверке."
    if gw and gw.giveaway_type == GiveawayType.randomizer:
        done_text = (
            "✅ Ответ отправлен!\n"
            "После одобрения админом вы будете участвовать в розыгрыше победителя."
        )
    await message.answer(done_text, reply_markup=back_to_menu_kb())


@router.callback_query(F.data.startswith("gw:snooze:"))
async def snooze_giveaway(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return
    gw_id = int(callback.data.split(":")[-1])
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        part = await get_participation(session, user.id, gw_id) if user else None
        if part:
            remind_at = utcnow() + timedelta(hours=24)
            session.add(SnoozeReminder(user_id=user.id, participation_id=part.id, remind_at=remind_at))
            await session.commit()
    await callback.answer("Напомним через 24 часа", show_alert=True)
